"""Qwen3-ASR STT plugin — 對接 demo_streaming.py 的 HTTP chunk streaming API。

協定（每個對話輪次）：
  1. POST /api/start                          → {"session_id": "<uuid>"}
  2. POST /api/chunk?session_id=xxx  (binary float32 @ 16kHz mono)
     → {"language": "<lang>", "text": "<partial>"}  (即時回傳)
  3. POST /api/finish?session_id=xxx          → 最終結果

LiveKit 音訊（48kHz stereo PCM16）會在送出前轉換為 Float32 16kHz mono。
"""

from __future__ import annotations

import asyncio
import audioop
import logging
import struct
from collections.abc import AsyncIterator

import httpx
from livekit.agents import stt, utils
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = logging.getLogger(__name__)

_TARGET_SAMPLE_RATE = 16000
_CHUNK_DURATION_S = 0.1   # 每次送 100ms 的音訊


def _to_float32_mono(frame: stt.AudioFrame) -> bytes:
    """將 LiveKit AudioFrame（48kHz stereo PCM16）轉為 Float32 16kHz mono bytes。"""
    data = bytes(frame.data)

    # 多聲道轉 mono
    if frame.num_channels > 1:
        data = audioop.tomono(data, 2, 0.5, 0.5)

    # 降採樣到 16kHz
    if frame.sample_rate != _TARGET_SAMPLE_RATE:
        data, _ = audioop.ratecv(data, 2, 1, frame.sample_rate, _TARGET_SAMPLE_RATE, None)

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
            # 1. 建立 session
            resp = await client.post(f"{self._base_url}/api/start")
            resp.raise_for_status()
            session_id = resp.json()["session_id"]
            logger.debug("Qwen3-ASR session started: %s", session_id)

            audio_buffer = bytearray()
            chunk_bytes = int(_TARGET_SAMPLE_RATE * _CHUNK_DURATION_S * 4)  # float32 = 4 bytes

            try:
                async for frame in self._input:
                    if isinstance(frame, stt.SentinelFrame):
                        break

                    audio_buffer.extend(_to_float32_mono(frame))

                    # 累積到 100ms 再送，減少 HTTP 請求數
                    while len(audio_buffer) >= chunk_bytes:
                        chunk = bytes(audio_buffer[:chunk_bytes])
                        audio_buffer = audio_buffer[chunk_bytes:]

                        chunk_resp = await client.post(
                            f"{self._base_url}/api/chunk",
                            params={"session_id": session_id},
                            content=chunk,
                            headers={"Content-Type": "application/octet-stream"},
                        )
                        if chunk_resp.status_code == 200:
                            data = chunk_resp.json()
                            text = data.get("text", "").strip()
                            if text:
                                self._queue.put_nowait(
                                    stt.SpeechEvent(
                                        type=stt.SpeechEventType.INTERIM_TRANSCRIPT,
                                        alternatives=[
                                            stt.SpeechData(
                                                text=text,
                                                language=data.get("language", "zh"),
                                                confidence=0.8,
                                            )
                                        ],
                                    )
                                )

                # 送出剩餘 buffer
                if audio_buffer:
                    await client.post(
                        f"{self._base_url}/api/chunk",
                        params={"session_id": session_id},
                        content=bytes(audio_buffer),
                        headers={"Content-Type": "application/octet-stream"},
                    )

                # 3. 結束 session，取得最終結果
                finish_resp = await client.post(
                    f"{self._base_url}/api/finish",
                    params={"session_id": session_id},
                )
                if finish_resp.status_code == 200:
                    data = finish_resp.json()
                    text = data.get("text", "").strip()
                    if text:
                        self._queue.put_nowait(
                            stt.SpeechEvent(
                                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                                alternatives=[
                                    stt.SpeechData(
                                        text=text,
                                        language=data.get("language", "zh"),
                                        confidence=1.0,
                                    )
                                ],
                            )
                        )

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
            session_id = resp.json()["session_id"]

            pcm = _to_float32_mono(buffer.to_frame())
            await client.post(
                f"{self._base_url}/api/chunk",
                params={"session_id": session_id},
                content=pcm,
                headers={"Content-Type": "application/octet-stream"},
            )

            finish = await client.post(
                f"{self._base_url}/api/finish",
                params={"session_id": session_id},
            )
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
