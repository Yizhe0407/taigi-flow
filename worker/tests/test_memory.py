from worker.pipeline.memory import SlidingWindowMemory


def test_empty_memory_returns_only_system_prompt() -> None:
    mem = SlidingWindowMemory(system_prompt="You are helpful.")
    msgs = mem.to_messages()
    assert msgs == [{"role": "system", "content": "You are helpful."}]


def test_five_turns_returns_eleven_messages() -> None:
    mem = SlidingWindowMemory(system_prompt="sys")
    for i in range(5):
        mem.add("user", f"u{i}")
        mem.add("assistant", f"a{i}")
    msgs = mem.to_messages()
    assert len(msgs) == 11  # 1 system + 10 history


def test_overflow_drops_oldest_pair() -> None:
    mem = SlidingWindowMemory(max_turns=3, system_prompt="sys")
    for i in range(4):
        mem.add("user", f"u{i}")
        mem.add("assistant", f"a{i}")
    msgs = mem.to_messages()
    # system + 3 pairs = 7
    assert len(msgs) == 7
    # first pair dropped
    assert msgs[1] == {"role": "user", "content": "u1"}


def test_clear_resets_history() -> None:
    mem = SlidingWindowMemory(system_prompt="sys")
    mem.add("user", "hi")
    mem.add("assistant", "hello")
    mem.clear()
    assert mem.to_messages() == [{"role": "system", "content": "sys"}]
    assert len(mem) == 0


def test_max_turns_3_drop_first_pair() -> None:
    mem = SlidingWindowMemory(max_turns=3, system_prompt="s")
    for i in range(4):
        mem.add("user", f"u{i}")
        mem.add("assistant", f"a{i}")
    msgs = mem.to_messages()
    roles_contents = [(m["role"], m["content"]) for m in msgs[1:]]
    assert ("user", "u0") not in roles_contents
    assert ("assistant", "a0") not in roles_contents
    assert ("user", "u1") in roles_contents


def test_len_returns_turn_count() -> None:
    mem = SlidingWindowMemory()
    assert len(mem) == 0
    mem.add("user", "hi")
    mem.add("assistant", "hey")
    assert len(mem) == 1
    mem.add("user", "bye")
    mem.add("assistant", "cya")
    assert len(mem) == 2


def test_no_orphan_assistant_after_overflow() -> None:
    mem = SlidingWindowMemory(max_turns=2, system_prompt="s")
    for i in range(3):
        mem.add("user", f"u{i}")
        mem.add("assistant", f"a{i}")
    msgs = mem.to_messages()
    # first message after system must be user
    assert msgs[1]["role"] == "user"
    # pairs must alternate
    for i in range(1, len(msgs) - 1, 2):
        assert msgs[i]["role"] == "user"
        assert msgs[i + 1]["role"] == "assistant"
