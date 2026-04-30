"""Tests for PipelineRunner timeout and error-classification paths (P3-05)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.pipeline.memory import SlidingWindowMemory
from worker.session.components import AgentComponents
from worker.session.runner import PipelineRunner

if TYPE_CHECKING:
    from worker.db.repositories import InteractionLogRepository

_AUDIO = b"\x00" * 320  # minimal fake PCM


def _mock_log_repo() -> InteractionLogRepository:
    repo: InteractionLogRepository = MagicMock()
    repo.log_turn = AsyncMock()  # type: ignore[assignment]
    return repo


def _mock_fallback() -> MagicMock:
    fb = MagicMock()
    fb.play = AsyncMock()
    return fb


def _mock_text_processor(taibun: str = "ta") -> MagicMock:
    result = MagicMock()
    result.hanlo = "h"
    result.taibun = taibun
    proc = MagicMock()
    proc.process.return_value = result
    return proc


def _make_runner(
    asr: object | None = None,
    llm: object | None = None,
    tts: object | None = None,
    fallback: MagicMock | None = None,
    asr_timeout: float = 10.0,
    llm_total_timeout: float = 30.0,
) -> tuple[PipelineRunner, MagicMock, MagicMock]:
    """Returns (runner, fallback_mock, log_repo_mock)."""
    fb = fallback or _mock_fallback()
    log_repo = _mock_log_repo()
    audio_source = MagicMock()
    audio_source.capture_frame = AsyncMock()

    components = AgentComponents(
        tts=tts,  # type: ignore[arg-type]
        asr=asr or MagicMock(),  # type: ignore[arg-type]
        llm=llm or MagicMock(),  # type: ignore[arg-type]
        memory=SlidingWindowMemory(system_prompt="sys"),
        text_processor=_mock_text_processor(),
        audio_source=audio_source,
        fallback=fb,  # type: ignore[arg-type]
        log_repo=log_repo,  # type: ignore[arg-type]
        session_id="test-session",
        agent_profile_id="test-profile",
    )
    runner = PipelineRunner(
        components,
        asr_timeout=asr_timeout,
        llm_total_timeout=llm_total_timeout,
    )
    return runner, fb, log_repo  # type: ignore[return-value]


def _asr_returning(text: str) -> MagicMock:
    async def _stream(_audio_gen: object):  # type: ignore[no-untyped-def]
        partial = MagicMock()
        partial.is_final = True
        partial.text = text
        yield partial

    asr = MagicMock()
    asr.stream = _stream
    return asr


def _llm_yielding(*tokens: str) -> MagicMock:
    async def _stream(**_kwargs: object):  # type: ignore[no-untyped-def]
        async def _gen():  # type: ignore[no-untyped-def]
            for t in tokens:
                yield t

        return _gen()

    llm = MagicMock()
    llm.stream = _stream
    return llm


# ── ASR error paths ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_asr_timeout_sets_flag_and_plays_fallback() -> None:
    async def _hanging_stream(_audio_gen: object):  # type: ignore[no-untyped-def]
        await asyncio.sleep(999)
        yield MagicMock(is_final=True, text="")  # unreachable

    asr = MagicMock()
    asr.stream = _hanging_stream
    runner, fb, log_repo = _make_runner(asr=asr, asr_timeout=0.05)

    await runner.process_utterance(_AUDIO)

    fb.play.assert_awaited_once_with("asr_timeout")
    assert log_repo.log_turn.call_args.kwargs["error_flag"] == "asr_timeout"


@pytest.mark.asyncio
async def test_asr_api_error_sets_flag_and_plays_fallback() -> None:
    async def _failing_stream(_audio_gen: object):  # type: ignore[no-untyped-def]
        raise RuntimeError("ASR service down")
        yield  # make it an async generator

    asr = MagicMock()
    asr.stream = _failing_stream
    runner, fb, log_repo = _make_runner(asr=asr)

    await runner.process_utterance(_AUDIO)

    fb.play.assert_awaited_once_with("asr_timeout")
    assert log_repo.log_turn.call_args.kwargs["error_flag"] == "asr_api_error"


# ── LLM error paths ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_first_token_timeout_sets_flag_and_plays_fallback() -> None:
    async def _timeout_stream(**_kwargs: object) -> object:
        raise TimeoutError("LLM first token timeout")

    llm = MagicMock()
    llm.stream = _timeout_stream
    runner, fb, log_repo = _make_runner(asr=_asr_returning("hello"), llm=llm)

    await runner.process_utterance(_AUDIO)

    fb.play.assert_awaited_once_with("llm_error")
    assert log_repo.log_turn.call_args.kwargs["error_flag"] == "llm_timeout"


@pytest.mark.asyncio
async def test_llm_api_error_sets_flag_and_plays_fallback() -> None:
    async def _error_stream(**_kwargs: object) -> object:
        raise ValueError("unexpected API response")

    llm = MagicMock()
    llm.stream = _error_stream
    runner, fb, log_repo = _make_runner(asr=_asr_returning("hello"), llm=llm)

    await runner.process_utterance(_AUDIO)

    fb.play.assert_awaited_once_with("llm_error")
    assert log_repo.log_turn.call_args.kwargs["error_flag"] == "llm_api_error"


@pytest.mark.asyncio
async def test_llm_total_timeout_after_first_token_sets_partial_flag() -> None:
    async def _slow_stream(**_kwargs: object):  # type: ignore[no-untyped-def]
        async def _gen():  # type: ignore[no-untyped-def]
            yield "hello"
            await asyncio.sleep(999)  # stall after first token
            yield " world"

        return _gen()

    llm = MagicMock()
    llm.stream = _slow_stream
    runner, fb, log_repo = _make_runner(
        asr=_asr_returning("hi"),
        llm=llm,
        llm_total_timeout=0.05,  # fires after first token
    )

    await runner.process_utterance(_AUDIO)

    fb.play.assert_not_awaited()
    assert log_repo.log_turn.call_args.kwargs["error_flag"] == "llm_partial"


# ── TTS error paths ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tts_exception_skips_sentence_and_continues() -> None:
    """TTS synthesis error skips the failed sentence; pipeline does not abort."""

    async def _broken_synth(text: str):  # type: ignore[no-untyped-def]
        raise RuntimeError("Piper synthesis failed")
        yield  # make it an async generator

    tts = MagicMock()
    tts.synthesize = _broken_synth
    # Two sentences: both TTS tasks fail, but pipeline completes normally
    llm = _llm_yielding("第一句。", "第二句。")
    runner, fb, log_repo = _make_runner(
        asr=_asr_returning("question"),
        llm=llm,
        tts=tts,
    )

    await runner.process_utterance(_AUDIO)

    # No fallback played — TTS errors are sentence-level, not fatal
    fb.play.assert_not_awaited()
    # Pipeline still completes: log_turn is called, no error_flag
    assert log_repo.log_turn.called
    assert log_repo.log_turn.call_args.kwargs["error_flag"] is None
