"""Session 狀態 — 每個對話 session 的運行時資料。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionState:
    """存放於 AgentSession.userdata，記錄對話運行時狀態。"""

    session_id: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    turn_count: int = 0
    total_conversions: int = 0
    total_conversion_ms: float = 0.0
    last_stt_text: str = ""
    last_llm_response: str = ""
    last_converted_output: str = ""
    warnings: list[str] = field(default_factory=list)

    def record_conversion(self, latency_ms: float) -> None:
        self.total_conversions += 1
        self.total_conversion_ms += latency_ms

    @property
    def avg_conversion_ms(self) -> float:
        if self.total_conversions == 0:
            return 0.0
        return self.total_conversion_ms / self.total_conversions
