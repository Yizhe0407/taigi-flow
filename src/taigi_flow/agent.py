"""TaigiAgent — 核心 Agent，覆寫 tts_node 插入文字轉換 + TTS 合成。"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING

from livekit import rtc
from livekit.agents import Agent, ModelSettings

from taigi_flow.monitoring import metrics
from taigi_flow.monitoring.traces import get_tracer
from taigi_flow.text_safety import sanitize_piper_text

if TYPE_CHECKING:
    from taigi_flow.protocols import Synthesizer, TextConverter

logger = logging.getLogger(__name__)

_TTS_SENTENCE_DELIMITERS = frozenset({"。", "！", "？", "!", "?", "\n"})
_DEFAULT_MIN_CHARS_PER_CHUNK = 24
_DEFAULT_MAX_SENTENCES_PER_CHUNK = 2


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
        min_chars_per_chunk: int = _DEFAULT_MIN_CHARS_PER_CHUNK,
        max_sentences_per_chunk: int = _DEFAULT_MAX_SENTENCES_PER_CHUNK,
    ):
        super().__init__(instructions=instructions)
        self._converter = converter
        self._synthesizer = synthesizer
        self._min_chars_per_chunk = max(1, min_chars_per_chunk)
        self._max_sentences_per_chunk = max(1, max_sentences_per_chunk)

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
    ) -> AsyncIterable[rtc.AudioFrame]:
        """覆寫 tts_node：繁中串流 → 文字轉換 → TTS 合成 → AudioFrame。"""
        metrics.turns_total.inc()

        sentence_buffer = ""
        pending_sentences: list[str] = []

        async for converted_chunk in self._converter.stream_convert(text):
            sentence_buffer += converted_chunk

            while any(d in sentence_buffer for d in _TTS_SENTENCE_DELIMITERS):
                idx = min(
                    sentence_buffer.index(d)
                    for d in _TTS_SENTENCE_DELIMITERS
                    if d in sentence_buffer
                )
                sentence = sentence_buffer[: idx + 1].strip()
                sentence_buffer = sentence_buffer[idx + 1 :]

                if not sentence:
                    continue

                pending_sentences.append(sentence)
                if self._should_flush_pending(pending_sentences):
                    async for frame in self._flush_pending_sentences(pending_sentences):
                        yield frame

        if sentence_buffer.strip():
            pending_sentences.append(sentence_buffer.strip())

        if pending_sentences:
            async for frame in self._flush_pending_sentences(pending_sentences):
                yield frame

    async def _synthesize_sentence(self, sentence: str) -> AsyncIterable[rtc.AudioFrame]:
        safe_sentence = sanitize_piper_text(sentence)
        if not safe_sentence:
            logger.warning("Skipping unspeakable sentence after sanitization: %r", sentence[:80])
            return

        if safe_sentence != sentence:
            logger.debug("Sanitized TTS sentence: %s", safe_sentence[:80])
        else:
            logger.debug("TTS sentence: %s", safe_sentence[:80])

        span = get_tracer().start_span("tts.synthesize")
        span.set_attribute("input.length", len(safe_sentence))
        t0 = time.perf_counter()
        try:
            async for frame in self._synthesizer.synthesize_frames(safe_sentence):
                yield frame
        finally:
            metrics.tts_duration_seconds.observe(time.perf_counter() - t0)
            span.end()

    def _should_flush_pending(self, pending_sentences: list[str]) -> bool:
        if len(pending_sentences) >= self._max_sentences_per_chunk:
            return True

        merged = sanitize_piper_text(" ".join(pending_sentences))
        return len(merged) >= self._min_chars_per_chunk

    async def _flush_pending_sentences(
        self,
        pending_sentences: list[str],
    ) -> AsyncIterable[rtc.AudioFrame]:
        merged = " ".join(sentence.strip() for sentence in pending_sentences).strip()
        pending_sentences.clear()
        if not merged:
            return

        async for frame in self._synthesize_sentence(merged):
            yield frame
