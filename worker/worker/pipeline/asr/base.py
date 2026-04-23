import io
import wave
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


def pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """Convert raw 16-bit mono PCM bytes to WAV."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return wav_io.getvalue()


@dataclass
class ASRPartial:
    """ASR 串流過程中的中間結果"""

    text: str
    is_final: bool
    confidence: float | None = None


class BaseASR(ABC):
    """所有 ASR 實作必須遵循此介面"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def warmup(self) -> None: ...

    @abstractmethod
    async def stream(
        self,
        audio_chunks: AsyncIterator[bytes],
    ) -> AsyncIterator[ASRPartial]:
        """接收 PCM 音訊 chunk，產出串流辨識結果。

        Args:
            audio_chunks: 16kHz mono PCM 音訊片段

        Yields:
            ASRPartial: partial 結果持續更新，最後會有一個 is_final=True
        """
        # This is an async generator, we must use yield
        yield ASRPartial(text="", is_final=True)
