"""Qwen ASR stream tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from livekit import rtc
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from taigi_flow.stt.qwen_asr import QwenASRSTT


def _audio_frame(*, sample_value: int = 1000, samples: int = 1600) -> rtc.AudioFrame:
    pcm = sample_value.to_bytes(2, "little", signed=True) * samples
    return rtc.AudioFrame(
        data=pcm,
        sample_rate=16000,
        num_channels=1,
        samples_per_channel=samples,
    )


class TestQwenASRStream:
    async def test_stream_ignores_silence_only_audio(self):
        stt = QwenASRSTT(base_url="http://localhost:8001")
        stream = stt.stream(conn_options=DEFAULT_API_CONNECT_OPTIONS)

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("taigi_flow.stt.qwen_asr.httpx.AsyncClient", return_value=client):
            stream.push_frame(_audio_frame(sample_value=0))
            stream.end_input()
            events = [event async for event in stream]

        assert events == []
        client.post.assert_not_called()

    async def test_stream_emits_interim_and_final_transcripts(self):
        stt = QwenASRSTT(base_url="http://localhost:8001")
        stream = stt.stream(conn_options=DEFAULT_API_CONNECT_OPTIONS)

        start_resp = AsyncMock()
        start_resp.raise_for_status = MagicMock()
        start_resp.aread = AsyncMock(return_value=b"")
        start_resp.json = MagicMock(return_value={"session_id": "session-1"})

        chunk_resp = AsyncMock()
        chunk_resp.raise_for_status = MagicMock()
        chunk_resp.aread = AsyncMock(return_value=b"")
        chunk_resp.json = MagicMock(return_value={"language": "zh-TW", "text": "逐字稿"})

        finish_resp = AsyncMock()
        finish_resp.raise_for_status = MagicMock()
        finish_resp.aread = AsyncMock(return_value=b"")
        finish_resp.json = MagicMock(return_value={"language": "zh-TW", "text": "完整句子"})

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(side_effect=[start_resp, chunk_resp, chunk_resp, finish_resp])

        with patch("taigi_flow.stt.qwen_asr.httpx.AsyncClient", return_value=client):
            stream.push_frame(_audio_frame())
            stream.push_frame(_audio_frame())
            stream.end_input()
            events = [event async for event in stream]

        assert [event.type for event in events] == [
            "interim_transcript",
            "final_transcript",
        ]
        assert events[0].alternatives[0].text == "逐字稿"
        assert events[1].alternatives[0].text == "完整句子"

    async def test_stream_ignores_single_noisy_chunk_before_speech_is_confirmed(self):
        stt = QwenASRSTT(base_url="http://localhost:8001")
        stream = stt.stream(conn_options=DEFAULT_API_CONNECT_OPTIONS)

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("taigi_flow.stt.qwen_asr.httpx.AsyncClient", return_value=client):
            stream.push_frame(_audio_frame())
            stream.end_input()
            events = [event async for event in stream]

        assert events == []
        client.post.assert_not_called()

    async def test_stream_does_not_send_silent_preroll_chunks(self):
        stt = QwenASRSTT(base_url="http://localhost:8001")
        stream = stt.stream(conn_options=DEFAULT_API_CONNECT_OPTIONS)

        start_resp = AsyncMock()
        start_resp.raise_for_status = MagicMock()
        start_resp.aread = AsyncMock(return_value=b"")
        start_resp.json = MagicMock(return_value={"session_id": "session-1"})

        chunk_resp = AsyncMock()
        chunk_resp.raise_for_status = MagicMock()
        chunk_resp.aread = AsyncMock(return_value=b"")
        chunk_resp.json = MagicMock(return_value={"language": "zh-TW", "text": "逐字稿"})

        finish_resp = AsyncMock()
        finish_resp.raise_for_status = MagicMock()
        finish_resp.aread = AsyncMock(return_value=b"")
        finish_resp.json = MagicMock(return_value={"language": "zh-TW", "text": "完整句子"})

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(side_effect=[start_resp, chunk_resp, chunk_resp, finish_resp])

        with patch("taigi_flow.stt.qwen_asr.httpx.AsyncClient", return_value=client):
            stream.push_frame(_audio_frame(sample_value=0))
            stream.push_frame(_audio_frame())
            stream.push_frame(_audio_frame())
            stream.end_input()
            events = [event async for event in stream]

        assert [event.type for event in events] == [
            "interim_transcript",
            "final_transcript",
        ]
        chunk_calls = [
            call for call in client.post.await_args_list
            if call.args and call.args[0] == "http://localhost:8001/api/chunk"
        ]
        assert len(chunk_calls) == 2

    async def test_stream_wraps_http_status_error_as_runtime_error(self):
        stt = QwenASRSTT(base_url="http://localhost:8001")
        stream = stt.stream(conn_options=DEFAULT_API_CONNECT_OPTIONS)

        start_resp = AsyncMock()
        start_resp.raise_for_status = MagicMock()
        start_resp.aread = AsyncMock(return_value=b"")
        start_resp.json = MagicMock(return_value={"session_id": "session-1"})

        chunk_resp = AsyncMock()
        chunk_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "boom",
            request=httpx.Request("POST", "http://localhost:8001/api/chunk"),
            response=httpx.Response(500),
        ))
        chunk_resp.status_code = 500
        chunk_resp.aread = AsyncMock(return_value=b'{"detail":"bad language"}')

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(side_effect=[start_resp, chunk_resp])

        with patch("taigi_flow.stt.qwen_asr.httpx.AsyncClient", return_value=client):
            stream.push_frame(_audio_frame())
            stream.push_frame(_audio_frame())
            stream.end_input()

            with pytest.raises(RuntimeError, match="Qwen3-ASR /api/chunk failed with HTTP 500"):
                async for _ in stream:
                    pass
