"""元件工廠 — 根據 config 建立所有元件實例。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livekit.agents import stt, llm
from livekit.plugins import openai

if TYPE_CHECKING:
    from taigi_flow.config import Settings
    from taigi_flow.protocols import Synthesizer, TextConverter


class ComponentFactory:
    """根據 Settings 中的 *_backend 欄位，建立對應的元件實例。

    新增 backend 只需：
    1. 在對應目錄新增實作檔案
    2. 在此 factory 加一個 case
    3. 在 .env 設定 backend 名稱
    """

    @staticmethod
    def create_stt(settings: Settings) -> stt.STT:
        match settings.stt_backend:
            case "qwen_asr":
                from taigi_flow.stt.qwen_asr import QwenASRSTT

                return QwenASRSTT(base_url=settings.qwen_asr_url)
            case "funasr":
                from taigi_flow.stt.funasr import FunASRSTT

                chunk_size = [int(x) for x in settings.funasr_chunk_size.split(",")]
                return FunASRSTT(
                    ws_url=settings.funasr_ws_url,
                    mode=settings.funasr_mode,
                    chunk_size=chunk_size,
                    chunk_interval=settings.funasr_chunk_interval,
                )
            case _:
                raise ValueError(f"Unknown STT backend: {settings.stt_backend}")

    @staticmethod
    def create_llm(settings: Settings) -> llm.LLM:
        match settings.llm_backend:
            case "ollama":
                return openai.LLM(
                    base_url=settings.llm_base_url,
                    model=settings.llm_model,
                    api_key="ollama",
                )
            case _:
                raise ValueError(f"Unknown LLM backend: {settings.llm_backend}")

    @staticmethod
    def create_converter(settings: Settings) -> TextConverter:
        match settings.converter_backend:
            case "hanloflow":
                from taigi_flow.converter.hanlo_bridge import HanloBridge

                return HanloBridge(data_dir=settings.hanloflow_data_dir)
            case "passthrough":
                from taigi_flow.converter.passthrough import PassthroughConverter

                return PassthroughConverter()
            case _:
                raise ValueError(f"Unknown converter backend: {settings.converter_backend}")

    @staticmethod
    def create_synthesizer(settings: Settings) -> Synthesizer:
        match settings.tts_backend:
            case "piper":
                from taigi_flow.tts.piper import PiperSynthesizer

                return PiperSynthesizer(
                    base_url=settings.piper_url,
                    voice=settings.piper_voice,
                    speed=settings.piper_speed,
                    noise_scale=settings.piper_noise_scale,
                    noise_scale_w=settings.piper_noise_scale_w,
                )
            case _:
                raise ValueError(f"Unknown TTS backend: {settings.tts_backend}")
