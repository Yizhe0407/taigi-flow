from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
_FALLBACK_MODEL = "BAAI/bge-m3"
_BATCH_SIZE = 32


class Embedder:
    """Wraps sentence-transformers; loaded once and reused.

    Set EMBEDDING_MODEL env var to pin a specific model and avoid the
    Qwen→BGE fallback (the two models have the same dim=1024 but different
    vector spaces, so mixing ingest and query models silently corrupts retrieval).
    """

    def __init__(self) -> None:
        self._model: object | None = None
        self._model_name: str | None = None

    @property
    def model_name(self) -> str | None:
        return self._model_name

    def load(self) -> None:
        from sentence_transformers import SentenceTransformer

        pinned = os.getenv("EMBEDDING_MODEL")
        candidates = [pinned] if pinned else [_DEFAULT_MODEL, _FALLBACK_MODEL]

        for model_id in candidates:
            try:
                logger.info("Loading embedding model %s …", model_id)
                self._model = SentenceTransformer(model_id, trust_remote_code=True)
                self._model_name = model_id
                logger.info("Embedding model %s loaded", model_id)
                return
            except Exception as e:
                logger.warning("Failed to load %s: %s", model_id, e)
                if pinned:
                    raise RuntimeError(
                        f"EMBEDDING_MODEL={pinned!r} failed to load"
                    ) from e

        raise RuntimeError(
            f"Could not load any embedding model ({_DEFAULT_MODEL}, {_FALLBACK_MODEL})"
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
