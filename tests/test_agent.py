"""TaigiAgent tests."""

from __future__ import annotations

from collections.abc import AsyncIterable
from unittest.mock import MagicMock

import pytest
from livekit.agents import ModelSettings

from taigi_flow.agent import TaigiAgent


async def _aiter(items: list[str]) -> AsyncIterable[str]:
    for item in items:
        yield item


class TestTaigiAgent:
    @pytest.mark.asyncio
    async def test_tts_node_merges_short_sentences_into_one_tts_chunk(self):
        converter = MagicMock()
        converter.stream_convert = MagicMock(
            return_value=_aiter(["li2 ho2", "--ah0！", " gua2 si7", " taigi."])
        )

        synthesizer = MagicMock()
        synthesizer.synthesize_frames = MagicMock(
            return_value=_aiter(["frame-1"])
        )

        agent = TaigiAgent(
            converter=converter,
            synthesizer=synthesizer,
            instructions="",
            min_chars_per_chunk=999,
        )

        frames = [
            frame
            async for frame in agent.tts_node(
                _aiter(["ignored"]),
                ModelSettings(),
            )
        ]

        assert frames == ["frame-1"]
        synthesizer.synthesize_frames.assert_called_once_with("li2 ho2--ah0 gua2 si7 taigi")

    @pytest.mark.asyncio
    async def test_tts_node_skips_sentence_that_becomes_empty_after_sanitization(self):
        converter = MagicMock()
        converter.stream_convert = MagicMock(return_value=_aiter(["ㄎㄨㄞˊ！", "li2 ho2！"]))

        synthesizer = MagicMock()
        synthesizer.synthesize_frames = MagicMock(return_value=_aiter(["frame-1"]))

        agent = TaigiAgent(
            converter=converter,
            synthesizer=synthesizer,
            instructions="",
        )

        frames = [
            frame
            async for frame in agent.tts_node(
                _aiter(["ignored"]),
                ModelSettings(),
            )
        ]

        assert frames == ["frame-1"]
        synthesizer.synthesize_frames.assert_called_once_with("li2 ho2")

    @pytest.mark.asyncio
    async def test_tts_node_flushes_after_max_sentences_threshold(self):
        converter = MagicMock()
        converter.stream_convert = MagicMock(
            return_value=_aiter(["li2 ho2！", "gua2 si7！", "tsin1 ho2！"])
        )

        synthesizer = MagicMock()
        synthesizer.synthesize_frames = MagicMock(
            side_effect=[
                _aiter(["frame-1"]),
                _aiter(["frame-2"]),
            ]
        )

        agent = TaigiAgent(
            converter=converter,
            synthesizer=synthesizer,
            instructions="",
            min_chars_per_chunk=999,
            max_sentences_per_chunk=2,
        )

        frames = [
            frame
            async for frame in agent.tts_node(
                _aiter(["ignored"]),
                ModelSettings(),
            )
        ]

        assert frames == ["frame-1", "frame-2"]
        assert synthesizer.synthesize_frames.call_args_list[0].args == ("li2 ho2 gua2 si7",)
        assert synthesizer.synthesize_frames.call_args_list[1].args == ("tsin1 ho2",)
