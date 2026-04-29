from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from livekit import rtc

if TYPE_CHECKING:
    from ..pipeline.text_processor import TextProcessor
    from ..pipeline.tts import PiperTTS

logger = logging.getLogger(__name__)

FallbackKind = Literal["asr_timeout", "llm_error", "tts_fail", "tool_error", "general"]

FALLBACK_TEXTS: dict[FallbackKind, str] = {
    "asr_timeout": "歹勢，我這馬聽無清楚，你閣講一遍好無？",
    "llm_error": "袂好勢，我拄才頭殼當機，請你閣問一擺。",
    "tts_fail": "拄才有小可問題，你閣講一遍。",
    "tool_error": "抱歉，外部資料這馬提無著，等一下才閣試看覓。",
    "general": "歹勢，出了一个小問題。",
}

_CHUNK = 640  # 20ms at 16kHz 16-bit mono


async def _push_pcm(pcm: bytes, audio_source: rtc.AudioSource) -> None:
    n_full = len(pcm) // _CHUNK
    for i in range(n_full):
        sub = pcm[i * _CHUNK : (i + 1) * _CHUNK]
        await audio_source.capture_frame(
            rtc.AudioFrame(
                data=sub,
                sample_rate=16000,
                num_channels=1,
                samples_per_channel=_CHUNK // 2,
            )
        )
    leftover = pcm[n_full * _CHUNK :]
    if leftover:
        padded = leftover + b"\x00" * (_CHUNK - len(leftover))
        await audio_source.capture_frame(
            rtc.AudioFrame(
                data=padded,
                sample_rate=16000,
                num_channels=1,
                samples_per_channel=_CHUNK // 2,
            )
        )


class FallbackPlayer:
    """Pregenerates 5 fallback audio clips at startup; plays them from memory."""

    def __init__(self, audio_source: rtc.AudioSource) -> None:
        self._audio_source = audio_source
        self._audios: dict[FallbackKind, bytes] = {}

    async def pregenerate(self, tts: PiperTTS, text_processor: TextProcessor) -> None:
        for kind, zh_text in FALLBACK_TEXTS.items():
            try:
                taibun = text_processor.process(zh_text).taibun
                chunks: list[bytes] = []
                async for chunk in tts.synthesize(taibun):
                    chunks.append(chunk)
                self._audios[kind] = b"".join(chunks)
            except Exception as e:
                logger.error("fallback pregeneration failed kind=%s error=%s", kind, e)
        logger.info(
            "fallback pregeneration complete kinds=%d/%d",
            len(self._audios),
            len(FALLBACK_TEXTS),
        )

    async def play(self, kind: FallbackKind) -> None:
        pcm = self._audios.get(kind)
        if pcm is None:
            logger.error(
                "fallback audio not available kind=%s (pregeneration may have failed)",
                kind,
            )
            return
        await _push_pcm(pcm, self._audio_source)

    @property
    def is_ready(self) -> bool:
        return len(self._audios) == len(FALLBACK_TEXTS)
