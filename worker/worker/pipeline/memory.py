from typing import Literal


class SlidingWindowMemory:
    def __init__(self, max_turns: int = 12, system_prompt: str = "") -> None:
        self.max_turns = max_turns
        self.system_prompt = system_prompt
        self.history: list[dict[str, str]] = []

    def add(self, role: Literal["user", "assistant"], content: str) -> None:
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-(self.max_turns * 2) :]

    def to_messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.system_prompt}] + self.history

    def clear(self) -> None:
        self.history.clear()

    def __len__(self) -> int:
        return len(self.history) // 2
