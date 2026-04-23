from __future__ import annotations

import dataclasses
import logging
import os
from typing import TYPE_CHECKING

from livekit import rtc

from ..db.repositories import AgentProfileRepository
from ..db.session import async_session_factory
from ..pipeline.asr.breeze import BreezeASR26
from ..pipeline.asr.qwen3 import Qwen3ASR
from ..pipeline.llm import LLMClient
from ..pipeline.memory import SlidingWindowMemory
from ..pipeline.text_processor import TextProcessor
from ..pipeline.tts import PiperTTS

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..pipeline.asr.base import BaseASR

logger = logging.getLogger("worker.session.components")

_FALLBACK_SYSTEM_PROMPT = (
    "你是一個會講台語的 AI 助理。"
    "請用繁體中文（漢羅混寫）回答，回覆要精簡（1-2 句），"
    "不要 emoji、不要括號註解、不要玩笑延伸。"
)


@dataclasses.dataclass
class AgentComponents:
    tts: PiperTTS | None
    asr: BaseASR
    llm: LLMClient
    memory: SlidingWindowMemory
    text_processor: TextProcessor
    audio_source: rtc.AudioSource


def _build_tts() -> PiperTTS | None:
    speaker_id: int | None = None
    raw = os.getenv("PIPER_SPEAKER_ID")
    if raw:
        try:
            speaker_id = int(raw)
        except ValueError:
            logger.warning("Invalid PIPER_SPEAKER_ID=%s, fallback to default", raw)
    try:
        tts = PiperTTS(
            model_path=os.getenv("PIPER_MODEL_PATH", "models/taigi.onnx"),
            speaker_id=speaker_id,
        )
        logger.info(
            "TTS backend: %s",
            f"HTTP ({tts.api_url})" if tts.api_url else "Local Piper model",
        )
        return tts
    except Exception as e:
        logger.warning("PiperTTS init failed: %s", e)
        return None


def _build_asr() -> BaseASR:
    asr_name = os.getenv("ASR_BACKEND", "qwen3").lower()
    if asr_name == "qwen3":
        return Qwen3ASR()
    if asr_name in {"breeze", "breeze26", "breeze-asr-26"}:
        return BreezeASR26()
    raise ValueError(
        f"Unsupported ASR_BACKEND='{asr_name}'. Expected qwen3 or breeze26."
    )


def _build_llm() -> LLMClient:
    base_url = os.getenv("LLM_BASE_URL") or os.getenv(
        "OPENAI_BASE_URL", "http://localhost:11434/v1"
    )
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "ollama")
    return LLMClient(
        base_url=base_url,
        api_key=api_key,
        model=os.getenv("LLM_MODEL", "frob/qwen3.5-instruct:9b"),
    )


async def _load_profile(db: AsyncSession, profile_name: str) -> tuple[str, str | None]:
    repo = AgentProfileRepository(db)
    profile = await repo.get_active_by_name(profile_name)
    if profile is None:
        logger.warning(
            "Profile '%s' not found or inactive, using fallback prompt.", profile_name
        )
        return _FALLBACK_SYSTEM_PROMPT, None
    logger.info("Using profile '%s' from database.", profile.name)
    return profile.systemPrompt, profile.id


async def build_components() -> AgentComponents:
    audio_source = rtc.AudioSource(16000, 1)
    tts = _build_tts()

    asr = _build_asr()
    logger.info("Warming up ASR: %s", asr.name)
    logger.info(
        "ASR config: backend=%s ASR_URL=%s QWEN3_ASR_URL=%s BREEZE_ASR_URL=%s",
        os.getenv("ASR_BACKEND", "qwen3"),
        os.getenv("ASR_URL"),
        os.getenv("QWEN3_ASR_URL"),
        os.getenv("BREEZE_ASR_URL"),
    )
    try:
        await asr.warmup()
    except Exception as e:
        logger.error("ASR warmup failed: %s", e)

    llm = _build_llm()

    profile_name = os.getenv("AGENT_PROFILE_NAME", "公車站長")
    async with async_session_factory() as db:
        system_prompt, profile_id = await _load_profile(db, profile_name)
        memory = SlidingWindowMemory(system_prompt=system_prompt)
        text_processor = TextProcessor(profile_id=profile_id, db_session=None)
        await text_processor.reload_if_updated(db)

    return AgentComponents(
        tts=tts,
        asr=asr,
        llm=llm,
        memory=memory,
        text_processor=text_processor,
        audio_source=audio_source,
    )
