# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
from collections.abc import AsyncIterator
from typing import Any

from .base import ASRPartial, BaseASR

try:
    from vllm import AsyncEngineArgs, AsyncLLMEngine  # type: ignore
except ImportError:
    AsyncEngineArgs = Any  # type: ignore
    AsyncLLMEngine = Any  # type: ignore


class Qwen3ASR(BaseASR):
    def __init__(self, model_path: str = "Qwen/Qwen3-ASR-0.6B") -> None:
        self.model_path = model_path
        self.engine_args = AsyncEngineArgs(  # type: ignore
            model=model_path,
            dtype="bfloat16",
            enforce_eager=False,  # 啟用 CUDA Graph 降低 TTFT
        )
        self.engine: AsyncLLMEngine | None = None  # type: ignore

    async def warmup(self) -> None:
        if self.engine is None:
            self.engine = AsyncLLMEngine.from_engine_args(self.engine_args)  # type: ignore
        await self._dummy_inference()

    async def _dummy_inference(self) -> None:
        # Dummy audio infer to trigger kernel compilation
        pass

    async def stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[ASRPartial]:
        if self.engine is None:
            raise RuntimeError("Engine not initialized. Call warmup() first.")

        # Qwen3-ASR 原生串流：累積 chunk 到 min_chunk_ms 後送入
        async for partial in self.engine.transcribe_stream(audio_chunks):  # type: ignore
            yield ASRPartial(
                text=partial.text,  # type: ignore
                is_final=partial.is_final,  # type: ignore
                confidence=partial.logprob,  # type: ignore
            )

    @property
    def name(self) -> str:
        return "qwen3-asr-0.6b"
