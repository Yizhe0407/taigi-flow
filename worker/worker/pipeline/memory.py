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

    def to_messages(
        self, extra_context: str = ""
    ) -> list[dict[str, str]]:
        """Return messages for LLM. extra_context is injected into the last user
        message only in the returned list — history is never mutated."""
        msgs: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ] + list(self.history)
        if extra_context and msgs and msgs[-1]["role"] == "user":
            msgs[-1] = {
                "role": "user",
                "content": f"{extra_context}\n{msgs[-1]['content']}",
            }
        return msgs

    def pop_last(self) -> None:
        if self.history:
            self.history.pop()

    def clear(self) -> None:
        self.history.clear()

    def __len__(self) -> int:
        return len(self.history) // 2
