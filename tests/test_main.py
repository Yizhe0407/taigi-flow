"""Entry-point smoke tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit import rtc
from livekit.agents import WorkerOptions

import taigi_flow.main as main_module


def test_main_runs_livekit_cli():
    with (
        patch.object(main_module, "_start_dashboard"),
        patch.object(main_module.agents.cli, "run_app") as run_app,
    ):
        main_module.main()

    run_app.assert_called_once()
    worker_options = run_app.call_args.args[0]
    assert isinstance(worker_options, WorkerOptions)
    assert worker_options.entrypoint_fnc is main_module.entrypoint
    assert worker_options.request_fnc is main_module.request_fnc
    assert worker_options.multiprocessing_context == "spawn"


@pytest.mark.asyncio
async def test_request_fnc_accepts_with_stable_agent_identity():
    req = SimpleNamespace(id="AJ_demo", accept=AsyncMock())

    await main_module.request_fnc(req)

    req.accept.assert_awaited_once_with(
        name="taigi-agent",
        identity="agent-AJ_demo",
    )


@pytest.mark.asyncio
async def test_connect_job_retries_with_locally_signed_token_on_401():
    connect = AsyncMock()
    ctx = SimpleNamespace(
        connect=AsyncMock(side_effect=rtc.ConnectError("401 Unauthorized - no permissions to access the room")),
        room=SimpleNamespace(connect=connect),
        job=SimpleNamespace(id="AJ_demo", room=SimpleNamespace(name="demo-room")),
        token_claims=lambda: SimpleNamespace(
            identity="agent-AJ_demo",
            video=SimpleNamespace(room="demo-room", room_join=False),
        ),
        _on_connect=lambda: None,
        _connected=False,
    )

    await main_module._connect_job(ctx)

    ctx.connect.assert_awaited_once()
    connect.assert_awaited_once()
    assert ctx._connected is True


def test_build_turn_handling_uses_configured_interruption_thresholds():
    with patch.object(main_module, "MultilingualModel", return_value="turn-detector"):
        turn_handling = main_module._build_turn_handling()

    assert turn_handling["interruption"] == {
        "enabled": True,
        "min_duration": 0.6,
        "min_words": 1,
        "false_interruption_timeout": 1.2,
        "resume_false_interruption": True,
        "discard_audio_if_uninterruptible": True,
    }
    assert turn_handling["turn_detection"] == "turn-detector"


@pytest.mark.asyncio
async def test_entrypoint_builds_agent_with_tts_chunk_settings():
    fake_session = AsyncMock()
    fake_session.on = MagicMock(side_effect=lambda *_args, **_kwargs: (lambda fn: fn))
    fake_room = SimpleNamespace(name="demo-room")
    ctx = SimpleNamespace(room=fake_room)

    with (
        patch.object(main_module, "_connect_job", AsyncMock()),
        patch.object(main_module, "register_session"),
        patch.object(main_module, "unregister_session"),
        patch.object(main_module.metrics.sessions_active, "inc"),
        patch.object(main_module, "AgentSession", return_value=fake_session),
        patch.object(main_module.factory, "create_stt", return_value="stt"),
        patch.object(main_module.factory, "create_llm", return_value="llm"),
        patch.object(main_module.factory, "create_converter", return_value="converter"),
        patch.object(main_module.factory, "create_synthesizer", return_value="synth"),
        patch.object(main_module, "TaigiAgent") as agent_cls,
        patch.object(main_module, "MultilingualModel", return_value="turn-detector"),
    ):
        await main_module.entrypoint(ctx)

    agent_cls.assert_called_once_with(
        converter="converter",
        synthesizer="synth",
        instructions=main_module.settings.agent_instructions,
        min_chars_per_chunk=24,
        max_sentences_per_chunk=2,
    )
