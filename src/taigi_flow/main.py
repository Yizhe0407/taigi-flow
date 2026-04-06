"""Taigi-Flow 入口 — AgentServer 設定與 session 組裝。"""

from __future__ import annotations

import asyncio
import logging

# 在所有 livekit import 之前載入 .env.local 到 os.environ
# livekit-agents 直接讀 LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")

import uvicorn
from livekit import agents
from livekit.agents import AgentSession, TurnHandlingOptions
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from taigi_flow.agent import TaigiAgent
from taigi_flow.config import Settings
from taigi_flow.factory import ComponentFactory
from taigi_flow.monitoring import dashboard_app, metrics, setup_tracing, shutdown_tracing
from taigi_flow.monitoring.dashboard import register_session, unregister_session

logger = logging.getLogger(__name__)

settings = Settings()
factory = ComponentFactory()
server = agents.AgentServer()


async def _start_dashboard() -> None:
    """在背景啟動監控後台（FastAPI + Prometheus /metrics）。"""
    config = uvicorn.Config(
        dashboard_app,
        host="0.0.0.0",
        port=settings.metrics_port,
        log_level="warning",
    )
    userver = uvicorn.Server(config)
    await userver.serve()


@server.rtc_session(agent_name="taigi-agent")
async def taigi_session(ctx: agents.JobContext) -> None:
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


async def _main() -> None:
    if settings.enable_tracing:
        setup_tracing(settings.otlp_endpoint)

    dashboard_task = asyncio.create_task(_start_dashboard())
    logger.info("Dashboard started on port %d", settings.metrics_port)

    try:
        await server.run()
    finally:
        dashboard_task.cancel()
        shutdown_tracing()


if __name__ == "__main__":
    agents.cli.run_app(server)
