from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING

from worker.observability.metrics import LatencyTimer

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


def _fake_perf_counter(times: list[float]) -> Callable[[], float]:
    """每次呼叫依序回傳 times 中的下一個值；耗盡後固定回最後一個。"""
    iterator = iter(times)
    last = times[-1]

    def _fn() -> float:
        nonlocal last
        with contextlib.suppress(StopIteration):
            last = next(iterator)
        return last

    return _fn


def test_start_then_finalize_total_is_near_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "perf_counter", _fake_perf_counter([0.0, 0.0]))
    timer = LatencyTimer.start()
    timer.finalize()
    assert timer.as_dict() == {"total": 0}


def test_mark_four_stages_monotonic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        time,
        "perf_counter",
        _fake_perf_counter([0.0, 0.3, 0.5, 0.8, 1.2]),
    )
    timer = LatencyTimer.start()
    timer.mark("asr_end")
    timer.mark("llm_first_tok")
    timer.mark("first_audio")
    timer.finalize()
    d = timer.as_dict()
    assert d == {
        "asr_end": 300,
        "llm_first_tok": 500,
        "first_audio": 800,
        "total": 1200,
    }
    assert d["asr_end"] < d["llm_first_tok"] < d["first_audio"] < d["total"]


def test_partial_marks_only_emit_recorded_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "perf_counter", _fake_perf_counter([0.0, 0.25, 0.6]))
    timer = LatencyTimer.start()
    timer.mark("asr_end")
    timer.mark("llm_first_tok")
    d = timer.as_dict()
    assert set(d.keys()) == {"asr_end", "llm_first_tok"}
    assert d == {"asr_end": 250, "llm_first_tok": 600}


def test_mark_same_stage_twice_overwrites_and_warns(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(time, "perf_counter", _fake_perf_counter([0.0, 0.1, 0.4]))
    timer = LatencyTimer.start()
    timer.mark("asr_end")
    with caplog.at_level(logging.WARNING, logger="worker.observability.metrics"):
        timer.mark("asr_end")
    assert timer.as_dict() == {"asr_end": 400}
    assert any(
        rec.levelno == logging.WARNING and "asr_end" in rec.getMessage()
        for rec in caplog.records
    )


def test_contains_reflects_mark_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "perf_counter", _fake_perf_counter([0.0, 0.1]))
    timer = LatencyTimer.start()
    assert "asr_end" not in timer
    assert "llm_first_tok" not in timer
    timer.mark("asr_end")
    assert "asr_end" in timer
    assert "llm_first_tok" not in timer


def test_perf_counter_truncates_to_int_ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "perf_counter", _fake_perf_counter([0.0, 0.1239]))
    timer = LatencyTimer.start()
    timer.mark("asr_end")
    assert timer.as_dict()["asr_end"] == 123


def test_as_dict_returns_independent_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "perf_counter", _fake_perf_counter([0.0, 0.5]))
    timer = LatencyTimer.start()
    timer.mark("asr_end")
    d = timer.as_dict()
    d["asr_end"] = 999
    assert timer.as_dict()["asr_end"] == 500
