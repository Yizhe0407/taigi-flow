"""應用程式設定 — 所有元件的 backend 選擇和連線設定。"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from taigi_flow.prompts import load_prompt


class Settings(BaseSettings):
    # === 元件選擇 ===
    stt_backend: str = "qwen_asr"
    llm_backend: str = "ollama"
    tts_backend: str = "piper"
    converter_backend: str = "hanloflow"

    # === STT (Qwen3-ASR HTTP Streaming) ===
    qwen_asr_url: str = "http://localhost:8001"   # demo_streaming.py server

    # === LLM ===
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "frob/qwen3.5-instruct:4b"
    llm_timeout_seconds: float = 120.0

    # === TTS (Piper) ===
    piper_url: str = "http://localhost:5000"
    piper_voice: str = "taigi_epoch1339"
    piper_speed: float = 1.1
    piper_noise_scale: float = 0.8
    piper_noise_scale_w: float = 0.8

    # === HanloFlow ===
    hanloflow_data_dir: Path = Path("./hanloflow/data")

    # === LiveKit ===
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "devsecret"

    # === 監控 ===
    metrics_port: int = 8090
    enable_tracing: bool = True
    otlp_endpoint: str = "http://localhost:4317"

    # === Agent ===
    agent_preemptive_generation: bool = False
    agent_allow_interruptions: bool = True
    agent_interruption_min_duration: float = 0.6
    agent_interruption_min_words: int = 1
    agent_false_interruption_timeout: float = 1.2
    agent_resume_false_interruption: bool = True
    agent_discard_audio_if_uninterruptible: bool = True
    agent_aec_warmup_duration: float = 1.0
    agent_tts_min_chars_per_chunk: int = 24
    agent_tts_max_sentences_per_chunk: int = 2
    agent_instructions_path: Path | None = None
    agent_greeting_instructions_path: Path | None = None
    agent_instructions: str = Field(
        default_factory=lambda: load_prompt("agent_instructions.md")
    )
    agent_greeting_instructions: str = Field(
        default_factory=lambda: load_prompt("greeting_instructions.md")
    )

    @model_validator(mode="after")
    def _apply_prompt_overrides(self) -> "Settings":
        if self.agent_instructions_path is not None:
            self.agent_instructions = self.agent_instructions_path.read_text(
                encoding="utf-8"
            ).strip()
        if self.agent_greeting_instructions_path is not None:
            self.agent_greeting_instructions = (
                self.agent_greeting_instructions_path.read_text(encoding="utf-8").strip()
            )
        return self

    model_config = {"env_file": ".env.local", "env_file_encoding": "utf-8"}
