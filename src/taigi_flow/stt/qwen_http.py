"""Qwen3 ASR STT plugin — 透過 WebSocket 串流音訊並接收辨識結果。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets
from livekit.agents import stt, utils
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = logging.getLogger(__name__)


class QwenRecognizeStream(stt.RecognizeStream):
    """WebSocket 串流辨識：持續傳送音訊 chunk，接收逐步辨識結果。"""

    def __init__(self, ws_url: str, model: str, conn_options: APIConnectOptions):
        super().__init__(conn_options=conn_options)
        self._ws_url = ws_url
        self._model = model

    async def _run(self) -> None:
        try:
            async with websockets.connect(self._ws_url) as ws:
                # 傳送初始設定
                await ws.send(json.dumps({
                    "model": self._model,
                    "sample_rate": 16000,
                    "encoding": "pcm_s16le",
                }))

                async def send_audio() -> None:
                    async for frame in self._input:
                        if isinstance(frame, stt.EndOfTurnEvent):
                            await ws.send(json.dumps({"type": "end_of_turn"}))
                            continue
                        await ws.send(frame.data.tobytes())
                    await ws.send(json.dumps({"type": "close"}))

                async def recv_results() -> None:
                    async for msg in ws:
                        data = json.loads(msg)
                        if data.get("type") == "final":
                            self._queue.put_nowait(
                                stt.SpeechEvent(
                                    type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                                    alternatives=[
                                        stt.SpeechData(
                                            text=data["text"],
                                            language=data.get("language", "zh-TW"),
                                            confidence=data.get("confidence", 1.0),
                                        )
                                    ],
                                )
                            )
                        elif data.get("type") == "partial":
                            self._queue.put_nowait(
                                stt.SpeechEvent(
                                    type=stt.SpeechEventType.INTERIM_TRANSCRIPT,
                                    alternatives=[
                                        stt.SpeechData(
                                            text=data["text"],
                                            language=data.get("language", "zh-TW"),
                                            confidence=data.get("confidence", 0.5),
                                        )
                                    ],
                                )
                            )
                        elif data.get("type") == "close":
                            break

                await asyncio.gather(send_audio(), recv_results())
        except Exception:
            logger.exception("QwenRecognizeStream error")
            raise


class QwenSTT(stt.STT):
    """Qwen3 ASR — WebSocket 串流語音辨識。"""

    def __init__(self, *, ws_url: str, model: str = "qwen3-asr"):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=True, interim_results=True)
        )
        self._ws_url = ws_url
        self._model = model

    @property
    def label(self) -> str:
        return f"qwen-stt/{self._model}"

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: str | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        # 批次辨識：將整段音訊一次送出
        import httpx

        http_url = self._ws_url.replace("ws://", "http://").replace("/ws", "/recognize")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                http_url,
                content=buffer.to_bytes(),
                headers={"Content-Type": "audio/pcm"},
                params={"model": self._model},
            )
            data = resp.json()
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        text=data["text"],
                        language=data.get("language", "zh-TW"),
                        confidence=data.get("confidence", 1.0),
                    )
                ],
            )

    def stream(
        self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> QwenRecognizeStream:
        return QwenRecognizeStream(self._ws_url, self._model, conn_options)
