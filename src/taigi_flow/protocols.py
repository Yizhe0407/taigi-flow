"""元件介面定義 — 所有可替換元件的 Protocol。"""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Protocol

from livekit import rtc


class TextConverter(Protocol):
    """文字轉換器介面（HanloFlow 或未來替代方案）。

    將 LLM 輸出的繁中文字轉換為 TTS 可消費的格式（如 Taibun 羅馬字）。
    """

    async def stream_convert(self, text_stream: AsyncIterable[str]) -> AsyncIterable[str]:
        """串流轉換：接收 LLM token 串流，產出轉換後的文字片段。"""
        ...

    def convert(self, text: str) -> str:
        """單次轉換：一次性將完整文字轉換。"""
        ...


class Synthesizer(Protocol):
    """TTS 合成器介面（Piper 或未來替代方案）。

    將文字合成為音訊框架，供 LiveKit 串流播放。
    """

    async def synthesize_frames(self, text: str) -> AsyncIterable[rtc.AudioFrame]:
        """將文字合成為 AudioFrame 串流。"""
        ...
