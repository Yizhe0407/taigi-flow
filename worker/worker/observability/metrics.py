from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

Stage = Literal["asr_end", "llm_first_tok", "first_audio", "total"]


def _empty_marks() -> dict[Stage, int]:
    return {}


@dataclass
class LatencyTimer:
    """單輪對話延遲計時器，所有時間以 T0（`start()` 呼叫時刻）為原點。

    使用模式：
        timer = LatencyTimer.start()
        # ...ASR 完成...
        timer.mark("asr_end")
        # ...LLM 首 token 回來...
        timer.mark("llm_first_tok")
        # ...TTS 第一個 chunk 送出...
        timer.mark("first_audio")
        timer.finalize()
        repo.log_turn(..., latencies=timer.as_dict())
    """

    _t0: float = 0.0
    _marks: dict[Stage, int] = field(default_factory=_empty_marks)

    @classmethod
    def start(cls) -> LatencyTimer:
        return cls(_t0=time.perf_counter())

    def mark(self, stage: Stage) -> None:
        elapsed_ms = int((time.perf_counter() - self._t0) * 1000)
        if stage in self._marks:
            logger.warning(
                "LatencyTimer.mark(%s) called twice; overwriting %dms with %dms",
                stage,
                self._marks[stage],
                elapsed_ms,
            )
        self._marks[stage] = elapsed_ms

    def finalize(self) -> None:
        self.mark("total")

    def as_dict(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for k, v in self._marks.items():
            out[k] = v
        return out

    def __contains__(self, stage: Stage) -> bool:
        return stage in self._marks
