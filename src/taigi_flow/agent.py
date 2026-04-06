"""TaigiAgent — 核心 Agent，覆寫 tts_node 插入文字轉換 + TTS 合成。"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING

from livekit import rtc
from livekit.agents import Agent, ModelSettings

from taigi_flow.monitoring import metrics

if TYPE_CHECKING:
    from taigi_flow.protocols import Synthesizer, TextConverter

logger = logging.getLogger(__name__)


class TaigiAgent(Agent):
    """台語對話 Agent。

    透過依賴注入接收 converter 和 synthesizer，
    不依賴任何具體實作。換元件只需改 factory config。
    """

    def __init__(
        self,
        *,
        converter: TextConverter,
        synthesizer: Synthesizer,
        instructions: str = "",
    ):
        super().__init__(instructions=instructions)
        self._converter = converter
        self._synthesizer = synthesizer

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
    ) -> AsyncIterable[rtc.AudioFrame]:
        """覆寫 tts_node：繁中串流 → 文字轉換 → TTS 合成 → AudioFrame。"""
        metrics.turns_total.inc()

        async for converted_chunk in self._converter.stream_convert(text):
            logger.debug("Converted chunk: %s", converted_chunk[:50])

            t0 = time.perf_counter()
            async for frame in self._synthesizer.synthesize_frames(converted_chunk):
                yield frame
            metrics.tts_duration_seconds.observe(time.perf_counter() - t0)
