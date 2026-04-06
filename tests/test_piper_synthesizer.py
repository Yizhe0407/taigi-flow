"""PiperSynthesizer 單元測試 — mock HTTP，驗證 WAV 解析與 AudioFrame 輸出。"""

from __future__ import annotations

import io
import struct
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taigi_flow.tts.piper import PiperSynthesizer


def _make_wav(sample_rate: int = 22050, duration_samples: int = 4410) -> bytes:
    """產生最小的有效 WAV (mono 16-bit)。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * duration_samples)
    return buf.getvalue()


class TestPiperSynthesizer:
    def _synth(self) -> PiperSynthesizer:
        return PiperSynthesizer(
            base_url="http://localhost:5000",
            voice="taigi_test",
        )

    @pytest.mark.asyncio
    async def test_empty_text_yields_nothing(self):
        synth = self._synth()
        frames = [f async for f in synth.synthesize_frames("   ")]
        assert frames == []

    @pytest.mark.asyncio
    async def test_wav_split_into_frames(self):
        synth = self._synth()
        wav_bytes = _make_wav(sample_rate=22050, duration_samples=22050)  # 1 second

        # mock httpx.AsyncClient.stream
        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = AsyncMock(return_value=_async_iter([wav_bytes]))

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_response)

        with patch("taigi_flow.tts.piper.httpx.AsyncClient", return_value=mock_client):
            frames = [f async for f in synth.synthesize_frames("taibun text")]

        # 1 second at 22050 Hz, 20ms per frame → ~50 frames
        assert len(frames) > 0
        for frame in frames:
            assert frame.sample_rate == 22050
            assert frame.num_channels == 1
            assert frame.samples_per_channel == 22050 * 20 // 1000

    @pytest.mark.asyncio
    async def test_incomplete_wav_yields_nothing(self):
        synth = self._synth()

        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = AsyncMock(return_value=_async_iter([b"\x00" * 10]))

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_response)

        with patch("taigi_flow.tts.piper.httpx.AsyncClient", return_value=mock_client):
            frames = [f async for f in synth.synthesize_frames("hello")]

        assert frames == []


async def _async_iter(items):
    for item in items:
        yield item
