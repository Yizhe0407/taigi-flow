"""Taigi-Flow 入口 — AgentServer 設定與 session 組裝。"""
# ruff: noqa: E402

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from taigi_flow.bootstrap import load_env_file

# 在所有 livekit import 之前載入 .env.local 到 os.environ
# livekit-agents 直接讀 LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
load_env_file(Path(__file__).resolve().parents[2] / ".env.local")

from livekit import agents, api, rtc
from livekit.agents import AgentSession, TurnHandlingOptions, WorkerOptions
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from taigi_flow.agent import TaigiAgent
from taigi_flow.config import Settings
from taigi_flow.factory import ComponentFactory
from taigi_flow.monitoring import metrics
from taigi_flow.monitoring.dashboard import register_session, unregister_session
from taigi_flow.monitoring.traces import setup_tracing, shutdown_tracing

logger = logging.getLogger(__name__)

settings = Settings()
factory = ComponentFactory()

if settings.enable_tracing:
    import atexit
    setup_tracing(settings.otlp_endpoint)
    atexit.register(shutdown_tracing)

_AGENT_NAME = "taigi-agent"


def _agent_identity(job_id: str) -> str:
    return f"agent-{job_id}"


def _build_turn_handling() -> TurnHandlingOptions:
    return TurnHandlingOptions(
        turn_detection=MultilingualModel(),
        interruption={
            "enabled": settings.agent_allow_interruptions,
            "min_duration": settings.agent_interruption_min_duration,
            "min_words": settings.agent_interruption_min_words,
            "false_interruption_timeout": settings.agent_false_interruption_timeout,
            "resume_false_interruption": settings.agent_resume_false_interruption,
            "discard_audio_if_uninterruptible": (
                settings.agent_discard_audio_if_uninterruptible
            ),
        },
    )


def _build_fallback_room_token(ctx: agents.JobContext) -> str:
    identity = ctx.token_claims().identity or _agent_identity(ctx.job.id)
    return (
        api.AccessToken(
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
        .with_identity(identity)
        .with_name(_AGENT_NAME)
        .with_kind("agent")
        .with_ttl(timedelta(minutes=30))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=ctx.job.room.name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                hidden=True,
                agent=True,
            )
        )
        .to_jwt()
    )


def _needs_room_token_fallback(exc: rtc.ConnectError) -> bool:
    return "no permissions to access the room" in str(exc).lower()


async def _connect_job(ctx: agents.JobContext) -> None:
    try:
        await ctx.connect()
        return
    except rtc.ConnectError as exc:
        if not _needs_room_token_fallback(exc):
            raise

        claims = ctx.token_claims()
        logger.warning(
            "LiveKit job token was rejected; retrying with locally signed room token",
            extra={
                "job_id": ctx.job.id,
                "room": ctx.job.room.name,
                "job_token_identity": claims.identity,
                "job_token_room": claims.video.room if claims.video else "",
                "job_token_room_join": claims.video.room_join if claims.video else None,
            },
        )

    room_options = rtc.RoomOptions(auto_subscribe=True)
    await ctx.room.connect(settings.livekit_url, _build_fallback_room_token(ctx), options=room_options)
    # JobContext has no public API to signal a manual connect; update the internal
    # state directly so the rest of the agent lifecycle proceeds normally.
    ctx._on_connect()
    ctx._connected = True


async def request_fnc(req: agents.JobRequest) -> None:
    await req.accept(
        name=_AGENT_NAME,
        identity=_agent_identity(req.id),
    )


async def entrypoint(ctx: agents.JobContext) -> None:
    """有人連入 room 時自動呼叫。"""
    await _connect_job(ctx)

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

    session = AgentSession(
        stt=factory.create_stt(settings),
        llm=factory.create_llm(settings),
        tts=None,  # tts_node 完全覆寫，不使用 plugin
        vad=silero.VAD.load(),
        preemptive_generation=settings.agent_preemptive_generation,
        aec_warmup_duration=settings.agent_aec_warmup_duration,
        turn_handling=_build_turn_handling(),
    )

    @session.on("close")
    def _on_close():
        metrics.sessions_active.dec()
        unregister_session(session_id)
        logger.info("Session ended: %s", session_id)

    agent = TaigiAgent(
        converter=factory.create_converter(settings),
        synthesizer=factory.create_synthesizer(settings),
        instructions=settings.agent_instructions,
        min_chars_per_chunk=settings.agent_tts_min_chars_per_chunk,
        max_sentences_per_chunk=settings.agent_tts_max_sentences_per_chunk,
    )

    await session.start(room=ctx.room, agent=agent)

    # 初始招呼
    await session.generate_reply(
        instructions=settings.agent_greeting_instructions
    )


def _start_dashboard() -> None:
    import uvicorn
    from taigi_flow.monitoring.dashboard import app as dashboard_app

    uvicorn.run(
        dashboard_app,
        host="0.0.0.0",
        port=settings.metrics_port,
        log_level="warning",
    )


def main() -> None:
    """Run the LiveKit worker CLI."""
    import threading

    thread = threading.Thread(target=_start_dashboard, daemon=True)
    thread.start()
    logger.info("Dashboard started on port %d", settings.metrics_port)

    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            request_fnc=request_fnc,
            multiprocessing_context="spawn",
        )
    )


if __name__ == "__main__":
    main()
