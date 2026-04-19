from worker.pipeline.splitter import SmartSplitter


def test_strong_break_cuts_immediately() -> None:
    s = SmartSplitter()
    result = s.feed("你好。")
    assert result == ["你好。"]


def test_medium_break_too_short_no_cut() -> None:
    s = SmartSplitter()
    result = s.feed("好，")
    assert result == []


def test_medium_break_long_enough_cuts() -> None:
    s = SmartSplitter()
    result = s.feed("請問今天天氣，")
    assert len(result) == 1
    assert result[0] == "請問今天天氣，"


def test_multi_token_accumulation() -> None:
    s = SmartSplitter()
    tokens = list("你好，我是Claude。")
    sentences: list[str] = []
    for tok in tokens:
        sentences.extend(s.feed(tok))
    rest = s.flush()
    all_text = "".join(sentences) + rest
    assert all_text == "你好，我是Claude。"
    assert len(sentences) >= 1


def test_force_cut_at_max_buffer() -> None:
    s = SmartSplitter()
    long_text = "甲" * 45
    result = s.feed(long_text)
    assert len(result) >= 1
    assert len(result[0]) == SmartSplitter.MAX_BUFFER_CHARS


def test_flush_returns_remaining_buffer() -> None:
    s = SmartSplitter()
    s.feed("剩餘內容")
    rest = s.flush()
    assert rest == "剩餘內容"
    assert s.flush() == ""


def test_empty_string_no_error() -> None:
    s = SmartSplitter()
    result = s.feed("")
    assert result == []


def test_consecutive_strong_breaks_no_empty_strings() -> None:
    s = SmartSplitter()
    result = s.feed("好。。。")
    for chunk in result:
        assert chunk.strip() != ""


def test_whitespace_only_no_cut() -> None:
    s = SmartSplitter()
    result = s.feed("   ")
    assert result == []


def test_english_with_period() -> None:
    # English period not a break point — buffer holds until strong break or max
    s = SmartSplitter()
    result = s.feed("use Python.")
    assert result == []
    assert s.buffer == "use Python."


def test_multiple_strong_breaks_in_one_feed() -> None:
    s = SmartSplitter()
    result = s.feed("你好。再見。")
    assert len(result) == 2


def test_medium_break_exactly_at_min_chars() -> None:
    # 6 chars + medium break = should cut
    s = SmartSplitter()
    # "甲乙丙丁戊己，" = 6 chars before 、
    result = s.feed("甲乙丙丁戊己，")
    assert len(result) == 1


def test_medium_break_below_min_chars_no_cut() -> None:
    s = SmartSplitter()
    result = s.feed("甲乙丙，")  # 3 chars < 6
    assert result == []


def test_flush_clears_buffer() -> None:
    s = SmartSplitter()
    s.feed("hello")
    s.flush()
    assert s.buffer == ""


def test_no_cut_weak_break_short() -> None:
    s = SmartSplitter()
    result = s.feed("hi、")
    assert result == []
