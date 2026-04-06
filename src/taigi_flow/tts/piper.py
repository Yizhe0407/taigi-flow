"""Piper TTS 合成器 — 呼叫 piper-tts-http-server 的 /v1/audio/speech 端點。"""

from __future__ import annotations

import io
import logging
import wave
from collections.abc import AsyncIterable

import httpx
from livekit import rtc

logger = logging.getLogger(__name__)


class PiperSynthesizer:
    """實作 Synthesizer protocol。

    透過 HTTP 呼叫 piper-tts-http-server，接收 WAV，
    解析為 rtc.AudioFrame 供 LiveKit 播放。

    API 請求格式：
        POST /v1/audio/speech
        {
            "model": "<voice>",
            "voice": "<voice>",
            "input": "<taibun text>",
            "response_format": "wav",
            "speed": 1.1,
            "noise_scale": 0.8,
            "noise_scale_w": 0.8
        }
    """

    def __init__(
        self,
        base_url: str,
        voice: str,
        speed: float = 1.1,
        noise_scale: float = 0.8,
        noise_scale_w: float = 0.8,
    ):
        self._base_url = base_url.rstrip("/")
        self._voice = voice
        self._speed = speed
        self._noise_scale = noise_scale
        self._noise_scale_w = noise_scale_w

    async def synthesize_frames(self, text: str) -> AsyncIterable[rtc.AudioFrame]:
        """將 Taibun 文字送至 Piper HTTP server，回傳 AudioFrame 串流。"""
        if not text.strip():
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/v1/audio/speech",
                json={
                    "model": self._voice,
                    "voice": self._voice,
                    "input": text,
                    "response_format": "wav",
                    "speed": self._speed,
                    "noise_scale": self._noise_scale,
                    "noise_scale_w": self._noise_scale_w,
                },
            ) as resp:
                resp.raise_for_status()
                raw = bytearray()
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    raw.extend(chunk)

        if len(raw) <= 44:  # WAV header 至少 44 bytes
            logger.warning("Piper returned empty or incomplete WAV for: %s", text[:50])
            return

        buf = io.BytesIO(bytes(raw))
        with wave.open(buf, "rb") as wf:
            sample_rate = wf.getframerate()
            num_channels = wf.getnchannels()
            pcm_data = wf.readframes(wf.getnframes())

        # 切成 20ms frame
        samples_per_frame = sample_rate * 20 // 1000
        frame_size = samples_per_frame * num_channels * 2  # 16-bit PCM

        for offset in range(0, len(pcm_data), frame_size):
            frame_data = pcm_data[offset : offset + frame_size]
            if len(frame_data) < frame_size:
                frame_data += b"\x00" * (frame_size - len(frame_data))
            yield rtc.AudioFrame(
                data=frame_data,
                sample_rate=sample_rate,
                num_channels=num_channels,
                samples_per_channel=samples_per_frame,
            )
