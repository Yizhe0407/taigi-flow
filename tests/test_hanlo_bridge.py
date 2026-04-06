"""HanloBridge 單元測試 — 句子緩衝邏輯（不需要載入 HanloFlow 模型）。"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from taigi_flow.converter.hanlo_bridge import HanloBridge, _SENTENCE_DELIMITERS


async def _tokens(*tokens: str) -> AsyncIterator[str]:
    for t in tokens:
        yield t


class TestSentenceBuffering:
    """驗證 stream_convert 的句子分界邏輯。"""

    def _make_bridge_with_mock(self, mock_fn=None):
        bridge = HanloBridge()
        bridge._convert_fn = mock_fn or (lambda text: f"[{text}]")
        return bridge

    @pytest.mark.asyncio
    async def test_single_sentence_with_delimiter(self):
        bridge = self._make_bridge_with_mock()
        tokens = _tokens("你好", "嗎", "。")
        results = [r async for r in bridge.stream_convert(tokens)]
        assert results == ["[你好嗎。]"]

    @pytest.mark.asyncio
    async def test_multiple_sentences(self):
        bridge = self._make_bridge_with_mock()
        tokens = _tokens("你好。", "再見。")
        results = [r async for r in bridge.stream_convert(tokens)]
        assert results == ["[你好。]", "[再見。]"]

    @pytest.mark.asyncio
    async def test_no_delimiter_flushes_at_end(self):
        bridge = self._make_bridge_with_mock()
        tokens = _tokens("沒有標點符號的句子")
        results = [r async for r in bridge.stream_convert(tokens)]
        assert results == ["[沒有標點符號的句子]"]

    @pytest.mark.asyncio
    async def test_empty_stream(self):
        bridge = self._make_bridge_with_mock()
        tokens = _tokens()
        results = [r async for r in bridge.stream_convert(tokens)]
        assert results == []

    @pytest.mark.asyncio
    async def test_whitespace_only_skipped(self):
        """純空白（沒有 delimiter）的 token 不產生輸出。"""
        bridge = self._make_bridge_with_mock()
        tokens = _tokens("   ", "  ")
        results = [r async for r in bridge.stream_convert(tokens)]
        assert results == []

    @pytest.mark.asyncio
    async def test_all_delimiters_split_correctly(self):
        bridge = self._make_bridge_with_mock()
        tokens = _tokens("句一！句二？句三，")
        results = [r async for r in bridge.stream_convert(tokens)]
        assert len(results) == 3
        assert results[0] == "[句一！]"
        assert results[1] == "[句二？]"
        assert results[2] == "[句三，]"

    @pytest.mark.asyncio
    async def test_mixed_token_boundary(self):
        """delimiter 可能落在 token 中間。"""
        bridge = self._make_bridge_with_mock()
        tokens = _tokens("句一。句", "二。")
        results = [r async for r in bridge.stream_convert(tokens)]
        assert results == ["[句一。]", "[句二。]"]

    def test_convert_sync(self):
        bridge = self._make_bridge_with_mock(lambda t: t.upper())
        result = bridge.convert("hello")
        assert result == "HELLO"

    def test_sentence_delimiters_set(self):
        assert "。" in _SENTENCE_DELIMITERS
        assert "！" in _SENTENCE_DELIMITERS
        assert "？" in _SENTENCE_DELIMITERS
        assert "，" in _SENTENCE_DELIMITERS
