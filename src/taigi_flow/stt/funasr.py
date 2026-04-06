"""FunASR WebSocket STT plugin — 對接 FunASR runtime 的 2-pass 串流辨識。

協定：
  1. 建立 WebSocket 連線（subprotocol="binary"）
  2. 傳送 JSON 設定訊息
  3. 持續傳送 raw PCM16/16kHz binary chunks
  4. 接收 JSON 結果（is_final=false 為即時，is_final=true 為校正後最終）
  5. 傳送 {"is_speaking": false} 結束串流
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import websockets
from livekit.agents import stt, utils
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = logging.getLogger(__name__)

# FunASR 需要 16kHz PCM16 音訊
_SAMPLE_RATE = 16000
_NUM_CHANNELS = 1
_BYTES_PER_SAMPLE = 2


def _calc_stride(chunk_size: list[int], chunk_interval: int) -> int:
    """計算每個 chunk 的 byte 數。"""
    return int(60 * chunk_size[1] / chunk_interval / 1000 * _SAMPLE_RATE * _BYTES_PER_SAMPLE)


class FunASRRecognizeStream(stt.RecognizeStream):
    """FunASR 2-pass WebSocket 串流辨識。"""

    def __init__(
        self,
        ws_url: str,
        mode: str,
        chunk_size: list[int],
        chunk_interval: int,
        conn_options: APIConnectOptions,
    ):
        super().__init__(conn_options=conn_options)
        self._ws_url = ws_url
        self._mode = mode
        self._chunk_size = chunk_size
        self._chunk_interval = chunk_interval
        self._stride = _calc_stride(chunk_size, chunk_interval)

    async def _run(self) -> None:
        try:
            async with websockets.connect(
                self._ws_url,
                subprotocols=["binary"],
                ping_interval=None,
            ) as ws:
                # 1. 傳送初始設定
                config = {
                    "mode": self._mode,
                    "chunk_size": self._chunk_size,
                    "chunk_interval": self._chunk_interval,
                    "encoder_chunk_look_back": 4,
                    "decoder_chunk_look_back": 1,
                    "wav_name": "livekit-stream",
                    "is_speaking": True,
                    "itn": True,
                }
                await ws.send(json.dumps(config))

                audio_buffer = bytearray()
                send_done = asyncio.Event()

                async def send_audio() -> None:
                    nonlocal audio_buffer
                    async for frame in self._input:
                        if isinstance(frame, stt.SentinelFrame):
                            break
                        # 重新取樣到 16kHz（LiveKit 通常是 48kHz）
                        pcm = _resample_frame(frame)
                        audio_buffer.extend(pcm)

                        # 以 stride 為單位傳送
                        while len(audio_buffer) >= self._stride:
                            chunk = bytes(audio_buffer[: self._stride])
                            audio_buffer = audio_buffer[self._stride :]
                            await ws.send(chunk)

                    # 傳送剩餘 buffer
                    if audio_buffer:
                        await ws.send(bytes(audio_buffer))

                    # 通知 FunASR 說話結束
                    await ws.send(json.dumps({"is_speaking": False}))
                    send_done.set()

                async def recv_results() -> None:
                    async for msg in ws:
                        if isinstance(msg, bytes):
                            continue
                        data = json.loads(msg)
                        text = data.get("text", "").strip()
                        if not text:
                            continue

                        is_final = data.get("is_final", False)
                        mode = data.get("mode", "")

                        # 2pass 模式下，offline 結果才是最終校正版本
                        if self._mode == "2pass":
                            if mode == "2pass-offline":
                                event_type = stt.SpeechEventType.FINAL_TRANSCRIPT
                            else:
                                event_type = stt.SpeechEventType.INTERIM_TRANSCRIPT
                        else:
                            event_type = (
                                stt.SpeechEventType.FINAL_TRANSCRIPT
                                if is_final
                                else stt.SpeechEventType.INTERIM_TRANSCRIPT
                            )

                        self._queue.put_nowait(
                            stt.SpeechEvent(
                                type=event_type,
                                alternatives=[
                                    stt.SpeechData(
                                        text=text,
                                        language="zh-TW",
                                        confidence=1.0,
                                    )
                                ],
                            )
                        )

                    # WebSocket 關閉時結束
                    send_done.set()

                await asyncio.gather(send_audio(), recv_results())

        except Exception:
            logger.exception("FunASRRecognizeStream error")
            raise


def _resample_frame(frame: stt.AudioFrame) -> bytes:
    """將 AudioFrame 轉換為 FunASR 需要的 16kHz mono PCM16。

    LiveKit 傳來的音訊通常是 48kHz，需要降採樣。
    簡單實作：直接取樣（生產環境建議用 scipy 或 resampy）。
    """
    import audioop  # noqa: PLC0415

    data = frame.data if isinstance(frame.data, (bytes, bytearray)) else bytes(frame.data)

    # 多聲道轉 mono
    if frame.num_channels > 1:
        data = audioop.tomono(data, _BYTES_PER_SAMPLE, 0.5, 0.5)

    # 降採樣到 16kHz
    if frame.sample_rate != _SAMPLE_RATE:
        data, _ = audioop.ratecv(
            data,
            _BYTES_PER_SAMPLE,
            1,
            frame.sample_rate,
            _SAMPLE_RATE,
            None,
        )

    return data


class FunASRSTT(stt.STT):
    """FunASR WebSocket STT — 支援 online / offline / 2pass 模式。"""

    def __init__(
        self,
        *,
        ws_url: str = "ws://localhost:10095",
        mode: str = "2pass",
        chunk_size: list[int] | None = None,
        chunk_interval: int = 10,
    ):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=True, interim_results=True)
        )
        self._ws_url = ws_url
        self._mode = mode
        self._chunk_size = chunk_size or [5, 10, 5]
        self._chunk_interval = chunk_interval

    @property
    def label(self) -> str:
        return f"funasr/{self._mode}"

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: str | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        # 批次辨識：走 offline 模式送完整音訊
        async with websockets.connect(
            self._ws_url, subprotocols=["binary"], ping_interval=None
        ) as ws:
            await ws.send(json.dumps({
                "mode": "offline",
                "wav_name": "batch",
                "is_speaking": True,
                "itn": True,
            }))
            pcm = _resample_frame(buffer.to_frame())
            await ws.send(pcm)
            await ws.send(json.dumps({"is_speaking": False}))

            async for msg in ws:
                if isinstance(msg, bytes):
                    continue
                data = json.loads(msg)
                text = data.get("text", "").strip()
                if text:
                    return stt.SpeechEvent(
                        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                        alternatives=[stt.SpeechData(text=text, language="zh-TW")],
                    )

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(text="", language="zh-TW")],
        )

    def stream(
        self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> FunASRRecognizeStream:
        return FunASRRecognizeStream(
            ws_url=self._ws_url,
            mode=self._mode,
            chunk_size=self._chunk_size,
            chunk_interval=self._chunk_interval,
            conn_options=conn_options,
        )
