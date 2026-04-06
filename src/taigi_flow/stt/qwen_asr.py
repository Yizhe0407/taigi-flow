"""Qwen3-ASR STT plugin — 對接 demo_streaming.py 的 HTTP chunk streaming API。

協定（每個對話輪次）：
  1. POST /api/start                          → {"session_id": "<uuid>"}
  2. POST /api/chunk?session_id=xxx  (binary float32 @ 16kHz mono)
     → {"language": "<lang>", "text": "<partial>"}  (即時回傳)
  3. POST /api/finish?session_id=xxx          → 最終結果

LiveKit 音訊（48kHz stereo PCM16）會在送出前轉換為 Float32 16kHz mono。
"""

from __future__ import annotations

import audioop
import logging
import os
import struct
from collections import deque

import httpx
from livekit.agents import stt, utils
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = logging.getLogger(__name__)

_TARGET_SAMPLE_RATE = 16000
_CHUNK_DURATION_S = 0.1   # 每次送 100ms 的音訊
_SILENCE_FLUSH_SECONDS = float(os.environ.get("QWEN_ASR_SILENCE_FLUSH_SECONDS", "0.4"))
_VOICE_START_RMS_THRESHOLD = int(os.environ.get("QWEN_ASR_VOICE_START_RMS_THRESHOLD", "600"))
_VOICE_CONTINUE_RMS_THRESHOLD = int(
    os.environ.get("QWEN_ASR_VOICE_CONTINUE_RMS_THRESHOLD", "400")
)
_MIN_SPEECH_START_CHUNKS = int(os.environ.get("QWEN_ASR_MIN_SPEECH_START_CHUNKS", "2"))
_MIN_EMIT_CHUNKS = int(os.environ.get("QWEN_ASR_MIN_EMIT_CHUNKS", "2"))
_PREROLL_CHUNKS = int(os.environ.get("QWEN_ASR_PREROLL_CHUNKS", "3"))


async def _raise_for_status(resp: httpx.Response, *, context: str) -> None:
    """Raise a picklable error with response detail when an HTTP call fails."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        detail = ""
        try:
            detail = (await resp.aread()).decode("utf-8", errors="replace").strip()
        except Exception:
            pass

        message = f"{context} failed with HTTP {resp.status_code}"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message) from None


def _to_pcm16_mono_16k(frame: stt.AudioFrame) -> bytes:
    """將 LiveKit AudioFrame 轉為 16kHz mono PCM16 bytes。"""
    data = bytes(frame.data)

    # 多聲道轉 mono
    if frame.num_channels > 1:
        data = audioop.tomono(data, 2, 0.5, 0.5)

    # 降採樣到 16kHz
    if frame.sample_rate != _TARGET_SAMPLE_RATE:
        data, _ = audioop.ratecv(data, 2, 1, frame.sample_rate, _TARGET_SAMPLE_RATE, None)

    return data


def _pcm16_to_float32_bytes(data: bytes) -> bytes:
    """PCM16 mono bytes → Float32 bytes。"""
    # PCM16 → float32
    num_samples = len(data) // 2
    floats = [struct.unpack_from("<h", data, i * 2)[0] / 32768.0 for i in range(num_samples)]
    return struct.pack(f"{num_samples}f", *floats)


class QwenASRStream(stt.RecognizeStream):
    """Qwen3-ASR HTTP chunk 串流辨識。"""

    def __init__(self, stt: "QwenASRSTT", base_url: str, conn_options: APIConnectOptions):
        super().__init__(stt=stt, conn_options=conn_options)
        self._base_url = base_url.rstrip("/")

    async def _run(self) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            pcm_buffer = bytearray()
            chunk_bytes = int(_TARGET_SAMPLE_RATE * _CHUNK_DURATION_S * 2)  # pcm16 = 2 bytes
            silence_duration = 0.0
            session_id: str | None = None
            sent_audio = False
            sent_chunk_count = 0
            speech_started = False
            voice_run_chunks = 0
            last_interim_text = ""
            preroll_chunks: deque[tuple[bytes, int]] = deque(maxlen=_PREROLL_CHUNKS)

            async def _start_session() -> str:
                resp = await client.post(f"{self._base_url}/api/start")
                await _raise_for_status(resp, context="Qwen3-ASR /api/start")
                started_session_id = resp.json()["session_id"]
                logger.debug("Qwen3-ASR session started: %s", started_session_id)
                return started_session_id

            def _emit_event(event_type: stt.SpeechEventType, data: dict, confidence: float) -> None:
                nonlocal last_interim_text
                text = data.get("text", "").strip()
                if not text:
                    return

                if event_type == stt.SpeechEventType.INTERIM_TRANSCRIPT:
                    if sent_chunk_count < _MIN_EMIT_CHUNKS or text == last_interim_text:
                        return
                    last_interim_text = text
                else:
                    if sent_chunk_count < _MIN_EMIT_CHUNKS:
                        return
                    last_interim_text = ""

                self._event_ch.send_nowait(
                    stt.SpeechEvent(
                        type=event_type,
                        alternatives=[
                            stt.SpeechData(
                                text=text,
                                language=data.get("language", "zh"),
                                confidence=confidence,
                            )
                        ],
                    )
                )

            async def _send_chunk(chunk: bytes) -> None:
                nonlocal session_id, sent_audio, sent_chunk_count
                if session_id is None:
                    session_id = await _start_session()

                chunk_resp = await client.post(
                    f"{self._base_url}/api/chunk",
                    params={"session_id": session_id},
                    content=_pcm16_to_float32_bytes(chunk),
                    headers={"Content-Type": "application/octet-stream"},
                )
                await _raise_for_status(chunk_resp, context="Qwen3-ASR /api/chunk")
                sent_audio = True
                sent_chunk_count += 1
                _emit_event(
                    stt.SpeechEventType.INTERIM_TRANSCRIPT,
                    chunk_resp.json(),
                    confidence=0.8,
                )

            async def _finalize_session() -> None:
                nonlocal session_id, sent_audio, sent_chunk_count, silence_duration
                nonlocal speech_started, voice_run_chunks, last_interim_text
                if session_id is None or not sent_audio:
                    session_id = None  # clean up if session started but nothing sent
                    return

                finish_resp = await client.post(
                    f"{self._base_url}/api/finish",
                    params={"session_id": session_id},
                )
                await _raise_for_status(finish_resp, context="Qwen3-ASR /api/finish")
                _emit_event(
                    stt.SpeechEventType.FINAL_TRANSCRIPT,
                    finish_resp.json(),
                    confidence=1.0,
                )
                session_id = None
                sent_audio = False
                sent_chunk_count = 0
                silence_duration = 0.0
                speech_started = False
                voice_run_chunks = 0
                last_interim_text = ""
                preroll_chunks.clear()

            try:
                async for frame in self._input_ch:
                    if isinstance(frame, self._FlushSentinel):
                        if pcm_buffer and speech_started:
                            final_chunk = bytes(pcm_buffer)
                            if audioop.rms(final_chunk, 2) >= _VOICE_CONTINUE_RMS_THRESHOLD:
                                await _send_chunk(final_chunk)
                            pcm_buffer.clear()
                        await _finalize_session()
                        continue

                    pcm_buffer.extend(_to_pcm16_mono_16k(frame))

                    # 累積到 100ms 再處理，先做本地靜音門檻，避免把背景雜訊送進 ASR 造成幻覺。
                    while len(pcm_buffer) >= chunk_bytes:
                        chunk = bytes(pcm_buffer[:chunk_bytes])
                        pcm_buffer = pcm_buffer[chunk_bytes:]
                        rms = audioop.rms(chunk, 2)

                        if not speech_started:
                            preroll_chunks.append((chunk, rms))
                            if rms >= _VOICE_START_RMS_THRESHOLD:
                                voice_run_chunks += 1
                            else:
                                voice_run_chunks = 0

                            if voice_run_chunks < _MIN_SPEECH_START_CHUNKS:
                                continue

                            speech_started = True
                            for preroll_chunk, preroll_rms in preroll_chunks:
                                if preroll_rms < _VOICE_CONTINUE_RMS_THRESHOLD:
                                    continue
                                await _send_chunk(preroll_chunk)
                            silence_duration = 0.0
                            voice_run_chunks = 0
                            preroll_chunks.clear()
                            continue

                        if rms >= _VOICE_CONTINUE_RMS_THRESHOLD:
                            await _send_chunk(chunk)
                            silence_duration = 0.0
                        else:
                            silence_duration += _CHUNK_DURATION_S
                            if silence_duration >= _SILENCE_FLUSH_SECONDS:
                                await _finalize_session()

                # 送出剩餘 buffer
                if pcm_buffer and speech_started:
                    final_chunk = bytes(pcm_buffer)
                    if audioop.rms(final_chunk, 2) >= _VOICE_CONTINUE_RMS_THRESHOLD:
                        await _send_chunk(final_chunk)

                await _finalize_session()

            except Exception:
                logger.exception("QwenASRStream error (session=%s)", session_id)
                raise


class QwenASRSTT(stt.STT):
    """Qwen3-ASR HTTP Streaming STT。

    對接 QwenLM/Qwen3-ASR 的 demo_streaming.py server。
    """

    def __init__(self, *, base_url: str = "http://localhost:8001"):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=True, interim_results=True)
        )
        self._base_url = base_url

    @property
    def label(self) -> str:
        return "qwen3-asr"

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: str | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        """批次辨識：一次送完整音訊。"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self._base_url}/api/start")
            await _raise_for_status(resp, context="Qwen3-ASR /api/start")
            session_id = resp.json()["session_id"]

            pcm = _to_pcm16_mono_16k(buffer.to_frame())
            chunk_resp = await client.post(
                f"{self._base_url}/api/chunk",
                params={"session_id": session_id},
                content=_pcm16_to_float32_bytes(pcm),
                headers={"Content-Type": "application/octet-stream"},
            )
            await _raise_for_status(chunk_resp, context="Qwen3-ASR /api/chunk")

            finish = await client.post(
                f"{self._base_url}/api/finish",
                params={"session_id": session_id},
            )
            await _raise_for_status(finish, context="Qwen3-ASR /api/finish")
            data = finish.json()
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        text=data.get("text", "").strip(),
                        language=data.get("language", "zh"),
                        confidence=1.0,
                    )
                ],
            )

    def stream(
        self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> QwenASRStream:
        return QwenASRStream(stt=self, base_url=self._base_url, conn_options=conn_options)
