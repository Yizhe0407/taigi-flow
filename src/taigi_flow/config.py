"""應用程式設定 — 所有元件的 backend 選擇和連線設定。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === 元件選擇 ===
    stt_backend: str = "qwen_asr"
    llm_backend: str = "ollama"
    tts_backend: str = "piper"
    converter_backend: str = "hanloflow"

    # === STT (Qwen3-ASR HTTP Streaming) ===
    qwen_asr_url: str = "http://localhost:8001"   # demo_streaming.py server

    # === STT (FunASR WebSocket，備用) ===
    funasr_ws_url: str = "ws://localhost:10095"
    funasr_mode: str = "2pass"
    funasr_chunk_size: str = "5,10,5"
    funasr_chunk_interval: int = 10

    # === LLM ===
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3.5:9b"

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
    agent_instructions: str = "你是一個台語對話助手。用繁體中文回答問題，回答要簡潔自然。"

    model_config = {"env_file": ".env.local", "env_file_encoding": "utf-8"}
