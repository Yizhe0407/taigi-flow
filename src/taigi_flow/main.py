"""Taigi-Flow 入口 — AgentServer 設定與 session 組裝。"""

from __future__ import annotations

import logging

# 在所有 livekit import 之前載入 .env.local 到 os.environ
# livekit-agents 直接讀 LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")

from livekit import agents
from livekit.agents import AgentSession, TurnHandlingOptions, WorkerOptions
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from taigi_flow.agent import TaigiAgent
from taigi_flow.config import Settings
from taigi_flow.factory import ComponentFactory
from taigi_flow.monitoring import metrics
from taigi_flow.monitoring.dashboard import register_session, unregister_session

logger = logging.getLogger(__name__)

settings = Settings()
factory = ComponentFactory()


async def entrypoint(ctx: agents.JobContext) -> None:
    """有人連入 room 時自動呼叫。"""
    await ctx.connect()

    session_id = ctx.room.name
    logger.info(
        "New session: room=%s, stt=%s, llm=%s, tts=%s, converter=%s",
        session_id,
        settings.stt_backend,
        settings.llm_backend,
        settings.tts_backend,
        settings.converter_backend,
    )

    metrics.sessions_active.inc()
    register_session(session_id, {
        "room": session_id,
        "stt": settings.stt_backend,
        "llm": settings.llm_backend,
        "tts": settings.tts_backend,
        "converter": settings.converter_backend,
    })

    try:
        session = AgentSession(
            stt=factory.create_stt(settings),
            llm=factory.create_llm(settings),
            tts=None,  # tts_node 完全覆寫，不使用 plugin
            vad=silero.VAD.load(),
            turn_handling=TurnHandlingOptions(
                turn_detection=MultilingualModel(),
            ),
        )

        agent = TaigiAgent(
            converter=factory.create_converter(settings),
            synthesizer=factory.create_synthesizer(settings),
            instructions=settings.agent_instructions,
        )

        await session.start(room=ctx.room, agent=agent)

        # 初始招呼
        await session.generate_reply(
            instructions="用台語向使用者打招呼，問有什麼需要幫忙的。"
        )

        await ctx.wait_for_disconnect()

    finally:
        metrics.sessions_active.dec()
        unregister_session(session_id)
        logger.info("Session ended: %s", session_id)


if __name__ == "__main__":
    agents.cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
