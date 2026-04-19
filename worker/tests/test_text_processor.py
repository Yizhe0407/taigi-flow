from unittest.mock import MagicMock

import pytest

from worker.db.models import PronunciationEntry
from worker.pipeline.text_processor import ProcessResult, TextProcessor


def _make_entry(term: str, replacement: str, priority: int = 0) -> PronunciationEntry:
    e = MagicMock(spec=PronunciationEntry)
    e.term = term
    e.replacement = replacement
    e.priority = priority
    e.profileId = None
    return e


def _processor_with_dict(entries: list[PronunciationEntry]) -> TextProcessor:
    tp = TextProcessor()
    tp._dictionary = sorted(entries, key=lambda e: (-e.priority, -len(e.term)))
    tp._dict_loaded = True
    return tp


def test_basic_conversion_returns_process_result() -> None:
    tp = TextProcessor()
    result = tp.process("你好")
    assert isinstance(result, ProcessResult)
    assert result.hanlo
    assert result.taibun


def test_empty_string_no_error() -> None:
    tp = TextProcessor()
    result = tp.process("")
    assert isinstance(result, ProcessResult)


def test_dictionary_hit_replaces_term() -> None:
    entry = _make_entry("公車", "bú-sū")
    tp = _processor_with_dict([entry])
    result = tp.process("公車到了")
    assert "bú-sū" in result.hanlo or "bú-sū" in result.taibun


def test_dictionary_priority_high_wins() -> None:
    low = _make_entry("台灣", "low-replacement", priority=0)
    high = _make_entry("台灣", "high-replacement", priority=10)
    tp = _processor_with_dict([low, high])
    result = tp.process("台灣")
    assert "high-replacement" in result.hanlo or "high-replacement" in result.taibun
    assert "low-replacement" not in result.hanlo


def test_dictionary_long_term_wins_over_short() -> None:
    short = _make_entry("公車", "bus", priority=0)
    long_ = _make_entry("公車路線", "route", priority=0)
    tp = _processor_with_dict([short, long_])
    result = tp.process("公車路線查詢")
    # long term matched first, short term no longer present
    assert "route" in result.hanlo or "route" in result.taibun


def test_no_dictionary_does_not_crash() -> None:
    tp = _processor_with_dict([])
    result = tp.process("台灣")
    assert result.taibun


@pytest.mark.asyncio
async def test_load_dictionary_no_session() -> None:
    tp = TextProcessor(profile_id=None, db_session=None)
    await tp.load_dictionary()
    assert tp._dict_loaded
    assert tp._dictionary == []
