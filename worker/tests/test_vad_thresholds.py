"""Tests for P4-04: dynamic VAD threshold adjustment via VoiceController callbacks."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from worker.audio.processor import AudioProcessor
from worker.audio.voice_controller import VoiceController, VoiceState


def _make_vad_mock() -> MagicMock:
    vad = MagicMock()
    vad.update_thresholds = MagicMock()
    return vad


def _make_processor(vc: VoiceController) -> tuple[AudioProcessor, MagicMock]:
    vad = _make_vad_mock()
    runner = MagicMock()
    proc = AudioProcessor(vad=vad, runner=runner, voice_controller=vc)  # type: ignore[arg-type]
    return proc, vad


def test_entering_thinking_raises_vad_threshold() -> None:
    vc = VoiceController()
    _, vad = _make_processor(vc)

    vc.transition(VoiceState.LISTENING)
    vc.transition(VoiceState.THINKING)

    vad.update_thresholds.assert_called_once_with(
        activation_threshold=0.6, min_speech_duration=0.15
    )


def test_entering_speaking_keeps_raised_threshold() -> None:
    vc = VoiceController()
    _, vad = _make_processor(vc)

    vc.transition(VoiceState.LISTENING)
    vc.transition(VoiceState.THINKING)
    vc.transition(VoiceState.SPEAKING)

    # Both THINKING and SPEAKING enter "busy" → called twice, both with same values.
    assert vad.update_thresholds.call_count == 2
    for call in vad.update_thresholds.call_args_list:
        assert call.kwargs == {"activation_threshold": 0.6, "min_speech_duration": 0.15}


def test_leaving_speaking_resets_vad_threshold() -> None:
    vc = VoiceController()
    _, vad = _make_processor(vc)

    vc.transition(VoiceState.LISTENING)
    vc.transition(VoiceState.THINKING)
    vc.transition(VoiceState.SPEAKING)
    vc.transition(VoiceState.IDLE)

    last_call = vad.update_thresholds.call_args_list[-1]
    assert last_call.kwargs == {
        "activation_threshold": 0.5,
        "min_speech_duration": 0.05,
    }


@pytest.mark.asyncio
async def test_barge_in_from_thinking_resets_threshold() -> None:
    """Transitioning THINKING → BARGED_IN must reset VAD to defaults."""
    vc = VoiceController()
    vad = _make_vad_mock()
    runner = MagicMock()
    runner.audio_source = MagicMock()
    runner.tts = None
    runner.cancel_current_turn = MagicMock()
    AudioProcessor(vad=vad, runner=runner, voice_controller=vc)  # type: ignore[arg-type]

    vc.transition(VoiceState.LISTENING)
    vc.transition(VoiceState.THINKING)
    vc.transition(VoiceState.BARGED_IN)
    await asyncio.sleep(0)  # allow _barge_in_cleanup task to run

    last_call = vad.update_thresholds.call_args_list[-1]
    assert last_call.kwargs == {
        "activation_threshold": 0.5,
        "min_speech_duration": 0.05,
    }
