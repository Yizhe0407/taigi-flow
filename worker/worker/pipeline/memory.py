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

    def inject_context(self, context: str) -> None:
        """Prepend ephemeral RAG context to the last user message for this turn only.
        Not stored in history — disappears when the next turn's add() replaces it."""
        if self.history and self.history[-1]["role"] == "user":
            self.history[-1] = {
                "role": "user",
                "content": f"{context}\n{self.history[-1]['content']}",
            }

    def pop_last(self) -> None:
        if self.history:
            self.history.pop()

    def clear(self) -> None:
        self.history.clear()

    def __len__(self) -> int:
        return len(self.history) // 2
