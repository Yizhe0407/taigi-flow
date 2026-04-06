"""SessionState 單元測試。"""

from __future__ import annotations

from taigi_flow.session.state import SessionState


class TestSessionState:
    def test_initial_state(self):
        s = SessionState(session_id="test-123")
        assert s.session_id == "test-123"
        assert s.turn_count == 0
        assert s.total_conversions == 0
        assert s.avg_conversion_ms == 0.0

    def test_record_conversion(self):
        s = SessionState()
        s.record_conversion(50.0)
        s.record_conversion(100.0)
        assert s.total_conversions == 2
        assert s.total_conversion_ms == 150.0
        assert s.avg_conversion_ms == 75.0

    def test_avg_conversion_no_divide_by_zero(self):
        s = SessionState()
        assert s.avg_conversion_ms == 0.0

    def test_warnings_list(self):
        s = SessionState()
        s.warnings.append("test warning")
        assert len(s.warnings) == 1
        assert s.warnings[0] == "test warning"
