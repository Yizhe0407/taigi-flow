# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
import asyncio
from collections.abc import AsyncIterator
from typing import Any

from .base import ASRPartial, BaseASR

try:
    import torch  # type: ignore
    from transformers import (  # type: ignore
        WhisperForConditionalGeneration,
        WhisperProcessor,
    )
except ImportError:
    torch = Any  # type: ignore
    WhisperProcessor = Any  # type: ignore
    WhisperForConditionalGeneration = Any  # type: ignore


class BreezeASR26(BaseASR):
    def __init__(self, model_path: str = "MediaTek-Research/Breeze-ASR-26") -> None:
        self.processor: Any = None
        self.model: Any = None
        self.model_path = model_path

    async def warmup(self) -> None:
        def _load() -> None:
            self.processor = WhisperProcessor.from_pretrained(self.model_path)  # type: ignore
            device = "cuda" if torch.cuda.is_available() else "cpu"  # type: ignore
            self.model = WhisperForConditionalGeneration.from_pretrained(  # type: ignore
                self.model_path,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,  # type: ignore
            ).to(device).eval()  # type: ignore

        await asyncio.to_thread(_load)

    async def stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[ASRPartial]:
        buffer = bytearray()
        async for chunk in audio_chunks:
            buffer.extend(chunk)

        text = await self._transcribe_full(bytes(buffer))
        yield ASRPartial(text=text, is_final=True)

    async def _transcribe_full(self, audio_bytes: bytes) -> str:
        if self.model is None or self.processor is None:
            raise RuntimeError("Model not loaded. Call warmup() first.")

        # Convert bytes to numpy array for processor
        def _process() -> str:
            import numpy as np

            # Assuming 16kHz mono PCM 16-bit
            audio_array = (
                np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )

            inputs = self.processor(
                audio_array, sampling_rate=16000, return_tensors="pt"
            )  # type: ignore
            inputs = inputs.to(self.model.device)  # type: ignore

            with torch.no_grad():  # type: ignore
                predicted_ids = self.model.generate(**inputs)  # type: ignore

            transcription: str = self.processor.batch_decode(
                predicted_ids, skip_special_tokens=True
            )[0]  # type: ignore
            return transcription

        return await asyncio.to_thread(_process)

    @property
    def name(self) -> str:
        return "breeze-asr-26"
