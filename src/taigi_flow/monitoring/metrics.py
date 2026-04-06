"""Prometheus 指標定義與設定。"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# 活躍 session 數
sessions_active = Gauge(
    "taigi_sessions_active",
    "Number of active voice sessions",
)

# 對話輪次總數
turns_total = Counter(
    "taigi_turns_total",
    "Total number of conversation turns",
)

# 文字轉換延遲（HanloFlow 或其他 converter）
conversion_duration_seconds = Histogram(
    "taigi_conversion_duration_seconds",
    "Time spent converting text (e.g. HanloFlow)",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# STT 延遲
stt_duration_seconds = Histogram(
    "taigi_stt_duration_seconds",
    "Time spent on speech-to-text",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

# TTS 延遲
tts_duration_seconds = Histogram(
    "taigi_tts_duration_seconds",
    "Time spent on text-to-speech synthesis",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

# LLM token 總數
llm_tokens_total = Counter(
    "taigi_llm_tokens_total",
    "Total LLM tokens generated",
    ["type"],  # input / output
)
