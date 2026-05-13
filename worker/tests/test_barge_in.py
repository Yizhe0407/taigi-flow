"""Tests for barge-in cancellation and cleanup sequence."""

from __future__ import annotations

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.audio.processor import AudioProcessor
from worker.audio.voice_controller import VoiceController, VoiceState
from worker.pipeline.memory import SlidingWindowMemory
from worker.session.components import AgentComponents
from worker.session.runner import PipelineRunner

_AUDIO = b"\x00" * 320


def _make_tts_mock() -> MagicMock:
    tts = MagicMock()
    tts.clear_queue = MagicMock()

    async def _empty_gen(_: str) -> object:
        return
        yield b""

    tts.synthesize = _empty_gen
    return tts


def _make_audio_source() -> MagicMock:
    src = MagicMock()
    src.capture_frame = AsyncMock()
    src.clear_queue = MagicMock()
    return src


def _make_runner(
    asr: object | None = None,
    llm: object | None = None,
    tts: object | None = None,
    asr_timeout: float = 10.0,
    llm_total_timeout: float = 30.0,
) -> tuple[PipelineRunner, MagicMock, MagicMock, MagicMock, VoiceController]:
    """Returns (runner, audio_source, log_repo, tts_mock, vc)."""
    log_repo: MagicMock = MagicMock()
    log_repo.log_turn = AsyncMock()

    fb: MagicMock = MagicMock()
    fb.play = AsyncMock()

    audio_source = _make_audio_source()
    tts_mock = tts or _make_tts_mock()
    vc = VoiceController()

    result_mock = MagicMock()
    result_mock.hanlo = "h"
    result_mock.taibun = ""
    text_proc = MagicMock()
    text_proc.process.return_value = result_mock

    components = AgentComponents(
        tts=tts_mock,  # type: ignore[arg-type]
        asr=asr or MagicMock(),  # type: ignore[arg-type]
        llm=llm or MagicMock(),  # type: ignore[arg-type]
        memory=SlidingWindowMemory(system_prompt="sys"),
        text_processor=text_proc,
        audio_source=audio_source,
        fallback=fb,  # type: ignore[arg-type]
        log_repo=log_repo,  # type: ignore[arg-type]
        session_id="test-session",
        agent_profile_id="test-profile",
        voice_controller=vc,
        realtime=AsyncMock(),
        agent_name="test-agent",
    )
    runner = PipelineRunner(
        components,
        asr_timeout=asr_timeout,
        llm_total_timeout=llm_total_timeout,
    )
    return runner, audio_source, log_repo, tts_mock, vc


def _asr_returning(text: str) -> MagicMock:
    async def _stream(_audio_gen: object) -> object:  # type: ignore[no-untyped-def]
        partial = MagicMock()
        partial.is_final = True
        partial.text = text
        yield partial

    asr = MagicMock()
    asr.stream = _stream
    return asr


def _llm_never_ends() -> MagicMock:
    async def _stream(messages: object, max_tokens: object = None) -> object:  # type: ignore[no-untyped-def]
        while True:
            yield "token"
            await asyncio.sleep(0.01)

    llm = MagicMock()
    llm.stream = AsyncMock(side_effect=_stream)
    return llm


# ── Fix 1: cancel_current_turn + generation counter ──────────────────────────

@pytest.mark.asyncio
async def test_cancel_current_turn_ends_quickly() -> None:
    runner, _, _, _, _ = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )
    task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    await asyncio.sleep(0.05)
    start = time.perf_counter()
    runner.cancel_current_turn()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200, f"cancel took {elapsed_ms:.1f}ms (expected <200ms)"


@pytest.mark.asyncio
async def test_cancel_immediately_unlocks_pipeline() -> None:
    """cancel_current_turn must set _pipeline_busy=False before the task exits."""
    runner, _, _, _, _ = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )
    task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    await asyncio.sleep(0.05)
    assert runner._pipeline_busy is True  # pyright: ignore[reportPrivateUsage]
    runner.cancel_current_turn()
    # Must be False immediately, before awaiting the task.
    assert runner._pipeline_busy is False  # pyright: ignore[reportPrivateUsage]
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_old_turn_finally_does_not_reset_pipeline_busy() -> None:
    """Generation counter: if a new turn starts, the old turn's finally must not
    reset _pipeline_busy and drop the new turn's work."""
    runner, _, _, _, _ = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )
    old_task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    await asyncio.sleep(0.05)

    # Barge-in: unlock immediately and cancel old task.
    runner.cancel_current_turn()
    assert runner._pipeline_busy is False  # pyright: ignore[reportPrivateUsage]

    # New turn starts before old task's finally block runs.
    new_task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test2")
    )
    await asyncio.sleep(0)  # yield so old task's finally can run

    # Old finally must NOT have reset _pipeline_busy for the new turn.
    assert runner._pipeline_busy is True  # pyright: ignore[reportPrivateUsage]

    new_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.gather(old_task, new_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_sets_was_barged_in_in_log() -> None:
    runner, _, log_repo, _, _ = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )
    task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    await asyncio.sleep(0.05)
    runner.cancel_current_turn()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)

    log_repo.log_turn.assert_called_once()
    assert log_repo.log_turn.call_args.kwargs["was_barged_in"] is True


# ── Fix 2: cleanup via AudioProcessor._barge_in_cleanup ──────────────────────

@pytest.mark.asyncio
async def test_barge_in_cleanup_clears_queues_and_cancels() -> None:
    """Transitioning to BARGED_IN must clear both audio/tts queues via on_change."""
    runner, audio_source, _, tts_mock, vc = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )
    vad_mock = MagicMock()
    vad_mock.update_thresholds = MagicMock()
    AudioProcessor(
        vad=vad_mock,  # type: ignore[arg-type]
        runner=runner,
        voice_controller=vc,
    )

    task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    await asyncio.sleep(0.05)

    # Trigger cleanup via FSM transition (the new API — no direct on_barge_in call).
    vc.transition(VoiceState.BARGED_IN)
    # Yield so the spawned _barge_in_cleanup task can run.
    await asyncio.sleep(0)

    tts_mock.clear_queue.assert_called_once()
    audio_source.clear_queue.assert_called_once()

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_voice_state_returns_listening_after_cancel() -> None:
    runner, _audio_source, _, _tts_mock, vc = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )
    vad_mock = MagicMock()
    vad_mock.update_thresholds = MagicMock()
    AudioProcessor(
        vad=vad_mock,  # type: ignore[arg-type]
        runner=runner,
        voice_controller=vc,
    )

    task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    await asyncio.sleep(0.05)

    vc.transition(VoiceState.BARGED_IN)
    await asyncio.sleep(0)

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)

    assert vc.state == VoiceState.LISTENING
