"""Tests for P4-04: dynamic VAD threshold adjustment via VoiceController callbacks."""

from __future__ import annotations

from unittest.mock import MagicMock

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


def test_entering_speaking_raises_vad_threshold() -> None:
    vc = VoiceController()
    _, vad = _make_processor(vc)

    # IDLE → LISTENING → THINKING → SPEAKING
    vc.transition(VoiceState.LISTENING)
    vc.transition(VoiceState.THINKING)
    vc.transition(VoiceState.SPEAKING)

    # update_thresholds should be called once with the high thresholds
    vad.update_thresholds.assert_called_once_with(
        activation_threshold=0.75, min_speech_duration=0.5
    )


def test_leaving_speaking_resets_vad_threshold() -> None:
    vc = VoiceController()
    _, vad = _make_processor(vc)

    vc.transition(VoiceState.LISTENING)
    vc.transition(VoiceState.THINKING)
    vc.transition(VoiceState.SPEAKING)
    vc.transition(VoiceState.IDLE)

    assert vad.update_thresholds.call_count == 2
    first_call = vad.update_thresholds.call_args_list[0]
    second_call = vad.update_thresholds.call_args_list[1]
    assert first_call.kwargs == {
        "activation_threshold": 0.75,
        "min_speech_duration": 0.5,
    }
    assert second_call.kwargs == {
        "activation_threshold": 0.5,
        "min_speech_duration": 0.3,
    }
