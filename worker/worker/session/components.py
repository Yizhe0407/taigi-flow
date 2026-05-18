from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from typing import TYPE_CHECKING

from livekit import rtc

from ..audio.fallback import FallbackPlayer
from ..audio.voice_controller import VoiceController
from ..db.repositories import AgentProfileRepository, InteractionLogRepository
from ..db.session import async_session_factory
from ..pipeline.asr.breeze import BreezeASR26
from ..pipeline.asr.qwen3 import Qwen3ASR
from ..pipeline.llm import LLMClient
from ..pipeline.memory import SlidingWindowMemory
from ..pipeline.rag import RagRetriever
from ..pipeline.realtime import RealtimePublisher
from ..pipeline.text_processor import TextProcessor
from ..pipeline.tts import PiperTTS
from ..tools import get_tools

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..ingest.embedder import Embedder
    from ..pipeline.asr.base import BaseASR
    from ..tools.base import BaseTool

logger = logging.getLogger("worker.session.components")

_embedder_singleton: Embedder | None = None


async def _get_embedder_async() -> Embedder:
    global _embedder_singleton
    if _embedder_singleton is None:
        from ..ingest.embedder import Embedder

        emb = Embedder()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, emb.load)
        _embedder_singleton = emb
    return _embedder_singleton

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
    fallback: FallbackPlayer
    log_repo: InteractionLogRepository | None
    session_id: str
    agent_profile_id: str | None
    voice_controller: VoiceController
    realtime: RealtimePublisher
    agent_name: str
    rag_retriever: RagRetriever | None = None
    tools: list[BaseTool] = dataclasses.field(default_factory=list)  # type: ignore[assignment]


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


_BUS_SYSTEM_PROMPT_FRAGMENT = """
你有公車工具。若使用者問：
- 「Y02 經過哪些站」→ bus.list_stops
- 「從 X 到 Y 怎麼搭」→ bus.find_routes（直達），若無 → 用 RAG 看異動公告
- 「Y02 接下來幾點」→ bus.next_departures（用班表）
- 「Y02 現在到哪」/「還多久到」→ tdx.bus_arrival（即時）
講站名與時間，不要念經緯度。"""

_BUS_TOOL_NAMES = {
    "bus.search_stops",
    "bus.find_routes",
    "bus.list_stops",
    "bus.next_departures",
    "tdx.bus_arrival",
}


async def _load_profile(
    db: AsyncSession,
) -> tuple[str, str | None, str, dict[str, object] | None, list[str]]:
    """Load the currently active profile from DB.

    Returns (system_prompt, profile_id, profile_name, rag_config, tool_names).
    """
    repo = AgentProfileRepository(db)
    profile = await repo.get_active()
    if profile is None:
        logger.warning("No active profile in DB, using fallback prompt.")
        return _FALLBACK_SYSTEM_PROMPT, None, "fallback", None, []
    logger.info("Loaded active profile '%s' (id=%s)", profile.name, profile.id)
    rag: dict[str, object] | None = (
        dict(profile.ragConfig) if profile.ragConfig else None  # type: ignore[arg-type]
    )
    tool_names: list[str] = list(profile.tools) if profile.tools else []  # type: ignore[arg-type]
    return profile.systemPrompt, profile.id, profile.name, rag, tool_names


async def build_components(livekit_room: str) -> AgentComponents:
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

    rag_retriever: RagRetriever | None = None
    rag_config: dict[str, object] | None
    tool_names: list[str]
    async with async_session_factory() as db:
        system_prompt, profile_id, profile_name, rag_config, tool_names = (
            await _load_profile(db)
        )
        # Import bus/tdx tools so they self-register via module-level register() calls
        if any(n.startswith(("bus.", "tdx.")) for n in tool_names):
            import worker.tools.bus  # type: ignore[import-untyped]  # noqa: F401
            import worker.tools.tdx_realtime  # type: ignore[import-untyped]  # noqa: F401

        tools = get_tools(tool_names)
        if tools:
            logger.info("Loaded tools: %s", [t.name for t in tools])

        # Append bus prompt fragment if bus tools are active
        if any(n in _BUS_TOOL_NAMES for n in tool_names):
            system_prompt = system_prompt + _BUS_SYSTEM_PROMPT_FRAGMENT

        memory = SlidingWindowMemory(system_prompt=system_prompt)
        text_processor = TextProcessor(profile_id=profile_id, db_session=None)
        await text_processor.reload_if_updated(db)

    if rag_config and rag_config.get("enabled") and rag_config.get("collectionId"):
        try:
            embedder = await _get_embedder_async()
            coll_id = str(rag_config["collectionId"])
            top_k = int(rag_config.get("topK") or 3)  # type: ignore[arg-type]
            threshold = float(rag_config.get("threshold") or 0.7)  # type: ignore[arg-type]
            rag_retriever = RagRetriever(
                embedder=embedder,
                session_factory=async_session_factory,
                collection_id=coll_id,
                top_k=top_k,
                threshold=threshold,
            )
            logger.info(
                "RAG enabled collection=%s topK=%d threshold=%.2f",
                coll_id,
                top_k,
                threshold,
            )
        except Exception as e:
            logger.error("RAG init failed, continuing without RAG: %s", e)

    fallback = FallbackPlayer(audio_source)
    if tts is not None:
        await fallback.pregenerate(tts, text_processor)

    log_repo: InteractionLogRepository | None
    session_id: str
    if profile_id is not None:
        log_repo = InteractionLogRepository(async_session_factory)
        session_id = await log_repo.create_session(profile_id, livekit_room)
        logger.info("Interaction logging enabled: session_id=%s", session_id)
    else:
        logger.warning(
            "Profile not found; interaction logging disabled for this session."
        )
        log_repo = None
        session_id = ""

    return AgentComponents(
        tts=tts,
        asr=asr,
        llm=llm,
        memory=memory,
        text_processor=text_processor,
        audio_source=audio_source,
        fallback=fallback,
        log_repo=log_repo,
        session_id=session_id,
        agent_profile_id=profile_id,
        voice_controller=VoiceController(),
        realtime=RealtimePublisher(),
        agent_name=profile_name,
        rag_retriever=rag_retriever,
        tools=tools,
    )
