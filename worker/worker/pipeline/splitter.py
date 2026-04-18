from typing import ClassVar


class SmartSplitter:
    STRONG_BREAKS: ClassVar[set[str]] = {"。", "！", "？", "\n"}
    MEDIUM_BREAKS: ClassVar[set[str]] = {"，", "；", "："}
    WEAK_BREAKS: ClassVar[set[str]] = {" ", "、"}
    MIN_CHARS_FOR_MEDIUM: ClassVar[int] = 6
    MAX_BUFFER_CHARS: ClassVar[int] = 40

    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, token: str) -> list[str]:
        self.buffer += token
        sentences: list[str] = []

        while True:
            cut_idx = self._find_cut_point()
            if cut_idx is None:
                break
            chunk = self.buffer[: cut_idx + 1]
            self.buffer = self.buffer[cut_idx + 1 :]
            if chunk.strip():
                sentences.append(chunk)

        return sentences

    def _find_cut_point(self) -> int | None:
        for i, ch in enumerate(self.buffer):
            if ch in self.STRONG_BREAKS:
                return i

        if len(self.buffer) >= self.MIN_CHARS_FOR_MEDIUM:
            for i, ch in enumerate(self.buffer):
                if ch in self.MEDIUM_BREAKS and i >= self.MIN_CHARS_FOR_MEDIUM - 1:
                    return i

        if len(self.buffer) >= self.MAX_BUFFER_CHARS:
            return self.MAX_BUFFER_CHARS - 1

        return None

    def flush(self) -> str:
        rest = self.buffer
        self.buffer = ""
        return rest
