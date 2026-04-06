"""Passthrough 轉換器 — 不做任何轉換，直接透傳文字（測試/除錯用）。"""

from __future__ import annotations

from collections.abc import AsyncIterable


class PassthroughConverter:
    """實作 TextConverter protocol，直接透傳不轉換。"""

    def convert(self, text: str) -> str:
        return text

    async def stream_convert(self, text_stream: AsyncIterable[str]) -> AsyncIterable[str]:
        async for token in text_stream:
            yield token
