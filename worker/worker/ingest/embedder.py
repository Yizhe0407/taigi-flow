from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_PRIMARY_MODEL = "Qwen/Qwen3-Embedding-0.6B"
_FALLBACK_MODEL = "BAAI/bge-m3"
_BATCH_SIZE = 32
_DIM = 1024


class Embedder:
    """Wraps sentence-transformers; loaded once and reused."""

    def __init__(self) -> None:
        self._model: object | None = None

    def load(self) -> None:
        from sentence_transformers import SentenceTransformer

        for model_name in (_PRIMARY_MODEL, _FALLBACK_MODEL):
            try:
                logger.info("Loading embedding model %s …", model_name)
                self._model = SentenceTransformer(model_name, trust_remote_code=True)
                logger.info("Embedding model %s loaded", model_name)
                return
            except Exception as e:
                logger.warning("Failed to load %s: %s, trying fallback", model_name, e)

        raise RuntimeError(
            f"Could not load any embedding model ({_PRIMARY_MODEL}, {_FALLBACK_MODEL})"
        )

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        from sentence_transformers import SentenceTransformer

        assert isinstance(self._model, SentenceTransformer)
        vecs = self._model.encode(  # type: ignore[assignment]
            texts,
            batch_size=_BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vecs]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            raise RuntimeError("Embedder.load() must be called before embed_batch()")
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._encode_sync, texts)

    async def embed_one(self, text: str) -> list[float]:
        vecs = await self.embed_batch([text])
        return vecs[0]
