from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from worker.audio.voice_controller import VoiceController, VoiceState


def test_initial_state() -> None:
    vc = VoiceController()
    assert vc.state == VoiceState.IDLE


def test_legal_full_turn() -> None:
    vc = VoiceController()
    vc.transition(VoiceState.LISTENING)
    assert vc.state == VoiceState.LISTENING
    vc.transition(VoiceState.THINKING)
    assert vc.state == VoiceState.THINKING
    vc.transition(VoiceState.SPEAKING)
    assert vc.state == VoiceState.SPEAKING
    vc.transition(VoiceState.IDLE)
    assert vc.state == VoiceState.IDLE


def test_barge_in_path() -> None:
    vc = VoiceController()
    vc.transition(VoiceState.LISTENING)
    vc.transition(VoiceState.THINKING)
    vc.transition(VoiceState.SPEAKING)
    vc.transition(VoiceState.BARGED_IN)
    assert vc.state == VoiceState.BARGED_IN
    vc.transition(VoiceState.LISTENING)
    assert vc.state == VoiceState.LISTENING


def test_illegal_transition_logs_warning_but_applies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging
    vc = VoiceController()
    with caplog.at_level(logging.WARNING, logger="worker.audio.voice_controller"):
        vc.transition(VoiceState.SPEAKING)
    assert vc.state == VoiceState.SPEAKING
    assert any("illegal transition" in r.message for r in caplog.records)


def test_on_change_callback_receives_correct_states() -> None:
    vc = VoiceController()
    events: list[tuple[VoiceState, VoiceState]] = []
    vc.on_change(lambda old, new: events.append((old, new)))
    vc.transition(VoiceState.LISTENING)
    assert events == [(VoiceState.IDLE, VoiceState.LISTENING)]


def test_multiple_callbacks_all_called() -> None:
    vc = VoiceController()
    calls: list[int] = []
    vc.on_change(lambda _o, _n: calls.append(1))
    vc.on_change(lambda _o, _n: calls.append(2))
    vc.transition(VoiceState.LISTENING)
    assert calls == [1, 2]


def test_mark_tts_output_and_time_since(monkeypatch: pytest.MonkeyPatch) -> None:
    vc = VoiceController()
    fake_now = 100.0

    monkeypatch.setattr(time, "perf_counter", lambda: fake_now)
    vc.mark_tts_output()

    fake_now = 100.5
    monkeypatch.setattr(time, "perf_counter", lambda: fake_now)
    ms = vc.time_since_last_tts_ms()
    assert abs(ms - 500.0) < 1e-6


def test_time_since_last_tts_before_mark() -> None:
    vc = VoiceController()
    assert vc.time_since_last_tts_ms() == float("inf")


def test_is_speaking_only_in_speaking_state() -> None:
    vc = VoiceController()
    assert not vc.is_speaking()
    vc.transition(VoiceState.LISTENING)
    assert not vc.is_speaking()
    vc.transition(VoiceState.THINKING)
    assert not vc.is_speaking()
    vc.transition(VoiceState.SPEAKING)
    assert vc.is_speaking()
    vc.transition(VoiceState.IDLE)
    assert not vc.is_speaking()


def test_no_callback_on_same_state() -> None:
    vc = VoiceController()
    calls: list[tuple[VoiceState, VoiceState]] = []
    vc.on_change(lambda o, n: calls.append((o, n)))
    vc.transition(VoiceState.IDLE)  # no-op
    assert calls == []
