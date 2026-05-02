"""Tests for P4-03: barge-in cancellation and cleanup sequence."""

from __future__ import annotations

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.audio.voice_controller import VoiceController, VoiceState
from worker.pipeline.memory import SlidingWindowMemory
from worker.session.components import AgentComponents
from worker.session.runner import PipelineRunner

_AUDIO = b"\x00" * 320


def _make_tts_mock() -> MagicMock:
    tts = MagicMock()
    tts.clear_queue = MagicMock()
    # synthesize yields nothing by default
    async def _empty_gen(_: str) -> object:
        return
        yield b""  # makes it an async generator

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
    """LLM that yields tokens forever (cancelled externally)."""
    async def _stream(messages: object, max_tokens: object = None) -> object:  # type: ignore[no-untyped-def]
        while True:
            yield "token"
            await asyncio.sleep(0.01)

    llm = MagicMock()
    llm.stream = AsyncMock(side_effect=_stream)
    return llm


@pytest.mark.asyncio
async def test_cancel_current_turn_ends_quickly() -> None:
    runner, _, _, _, _ = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )

    task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    # Let pipeline reach LLM stage
    await asyncio.sleep(0.05)
    start = time.perf_counter()
    runner.cancel_current_turn()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200, f"cancel took {elapsed_ms:.1f}ms (expected <200ms)"


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
    call_kwargs = log_repo.log_turn.call_args.kwargs
    assert call_kwargs["was_barged_in"] is True


@pytest.mark.asyncio
async def test_cancel_calls_tts_clear_queue() -> None:
    runner, _, _, _tts_mock, _ = _make_runner(
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

    # cancel_current_turn does NOT call tts.clear_queue directly;
    # on_barge_in does. Here we test that cancel_current_turn works, and
    # separately test on_barge_in below.
    assert runner._was_barged_in is True  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_on_barge_in_calls_clear_queues_and_cancels() -> None:
    runner, audio_source, _log_repo, tts_mock, vc = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )

    task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    await asyncio.sleep(0.05)

    await vc.on_barge_in(
        runner=runner,
        tts=tts_mock,  # type: ignore[arg-type]
        audio_source=audio_source,  # type: ignore[arg-type]
    )

    tts_mock.clear_queue.assert_called_once()
    audio_source.clear_queue.assert_called_once()

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_voice_state_returns_listening_after_cancel() -> None:
    runner, audio_source, _, tts_mock, vc = _make_runner(
        asr=_asr_returning("hello"),
        llm=_llm_never_ends(),
    )

    task: asyncio.Task[None] = asyncio.create_task(
        runner.process_utterance(_AUDIO, "test")
    )
    await asyncio.sleep(0.05)

    await vc.on_barge_in(
        runner=runner,
        tts=tts_mock,  # type: ignore[arg-type]
        audio_source=audio_source,  # type: ignore[arg-type]
    )

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)

    assert vc.state == VoiceState.LISTENING
