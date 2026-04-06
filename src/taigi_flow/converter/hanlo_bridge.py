"""HanloFlow 非同步橋接 — 將 LLM 串流 token 緩衝為句子，經 HanloFlow pipeline 轉換。

Pipeline：繁中文字 → TaigiConverter（台語漢字）→ TaibunRomanizer（Taibun）
使用 pipeline.convert_zh_to_taigi_taibun() 一次完成兩個步驟。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterable
from pathlib import Path

logger = logging.getLogger(__name__)

# 句子分界符號
_SENTENCE_DELIMITERS = frozenset({"。", "！", "？", "，", "；", "\n"})


class HanloBridge:
    """實作 TextConverter protocol。

    從 LLM 串流接收 token，以中文標點為界緩衝成句子，
    每句經 HanloFlow convert_zh_to_taigi_taibun() 轉換後產出 Taibun 羅馬字。
    """

    def __init__(self, data_dir: Path | str | None = None):
        self._data_dir = Path(data_dir) if data_dir else None
        self._convert_fn = None

    def _ensure_pipeline(self):
        if self._convert_fn is not None:
            return

        hanloflow_path = Path(__file__).resolve().parents[3] / "hanloflow"
        if str(hanloflow_path) not in sys.path:
            sys.path.insert(0, str(hanloflow_path))

        from pipeline import convert_zh_to_taigi_taibun
        from converter import TaigiConverter

        kwargs = {}
        if self._data_dir:
            kwargs["data_dir"] = self._data_dir
        converter = TaigiConverter(**kwargs)

        # 固定 converter 實例，避免每次重新載入
        def _convert(text: str) -> str:
            result = convert_zh_to_taigi_taibun(text, converter=converter)
            return result.taibun_number_tone

        self._convert_fn = _convert
        logger.info("HanloFlow pipeline initialized (data_dir=%s)", self._data_dir)

    def convert(self, text: str) -> str:
        """單次同步轉換，回傳 Taibun 羅馬字。"""
        self._ensure_pipeline()
        return self._convert_fn(text)

    async def stream_convert(self, text_stream: AsyncIterable[str]) -> AsyncIterable[str]:
        """串流轉換：緩衝 token 成句子，逐句轉換產出 Taibun 羅馬字。"""
        self._ensure_pipeline()
        buffer = ""

        async for token in text_stream:
            buffer += token

            while any(d in buffer for d in _SENTENCE_DELIMITERS):
                idx = min(
                    buffer.index(d) for d in _SENTENCE_DELIMITERS if d in buffer
                )
                sentence = buffer[: idx + 1]
                buffer = buffer[idx + 1 :]

                if sentence.strip():
                    result = await asyncio.to_thread(self._convert_fn, sentence.strip())
                    yield result

        if buffer.strip():
            result = await asyncio.to_thread(self._convert_fn, buffer.strip())
            yield result
