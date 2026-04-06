"""PiperSynthesizer 單元測試 — mock HTTP，驗證 WAV 解析與 AudioFrame 輸出。"""

from __future__ import annotations

import io
import wave
from unittest.mock import AsyncMock, patch

import httpx
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

        mock_response = AsyncMock()
        mock_response.is_error = False
        mock_response.aread = AsyncMock(return_value=wav_bytes)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("taigi_flow.tts.piper.httpx.AsyncClient", return_value=mock_client):
            frames = [f async for f in synth.synthesize_frames("taibun text")]

        # 1 second at 22050 Hz, 20ms per frame → ~50 frames
        assert len(frames) > 0
        for frame in frames:
            assert frame.sample_rate == 22050
            assert frame.num_channels == 1
            assert frame.samples_per_channel == 22050 * 40 // 1000

    @pytest.mark.asyncio
    async def test_incomplete_wav_yields_nothing(self):
        synth = self._synth()

        mock_response = AsyncMock()
        mock_response.is_error = False
        mock_response.aread = AsyncMock(return_value=b"\x00" * 10)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("taigi_flow.tts.piper.httpx.AsyncClient", return_value=mock_client):
            frames = [f async for f in synth.synthesize_frames("hello")]

        assert frames == []

    @pytest.mark.asyncio
    async def test_http_error_includes_response_detail(self):
        synth = self._synth()

        request = httpx.Request("POST", "http://localhost:5000/v1/audio/speech")
        mock_response = AsyncMock()
        mock_response.is_error = True
        mock_response.status_code = 404
        mock_response.request = request
        mock_response.aread = AsyncMock(return_value=b'{"detail":"Voice not found"}')

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with (
            patch("taigi_flow.tts.piper.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(httpx.HTTPStatusError, match="Voice not found"),
        ):
            frames = [f async for f in synth.synthesize_frames("hello")]
            assert frames == []

    @pytest.mark.asyncio
    async def test_remote_protocol_error_is_wrapped_as_runtime_error(self):
        synth = self._synth()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.RemoteProtocolError("boom"))

        with (
            patch("taigi_flow.tts.piper.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(RuntimeError, match="Piper stream closed unexpectedly"),
        ):
            frames = [f async for f in synth.synthesize_frames("li2 ho2")]
            assert frames == []

    @pytest.mark.asyncio
    async def test_client_is_reused_between_requests(self):
        synth = self._synth()

        wav_bytes = _make_wav(sample_rate=22050, duration_samples=2205)
        mock_response = AsyncMock()
        mock_response.is_error = False
        mock_response.aread = AsyncMock(return_value=wav_bytes)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("taigi_flow.tts.piper.httpx.AsyncClient", return_value=mock_client) as client_cls:
            _ = [f async for f in synth.synthesize_frames("li2 ho2")]
            _ = [f async for f in synth.synthesize_frames("gua2 si7")]

        client_cls.assert_called_once()
        assert mock_client.post.await_count == 2
