from __future__ import annotations

import dataclasses
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from worker.ingest.embedder import Embedder

logger = logging.getLogger(__name__)


def _metadata_dict(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    metadata = cast("dict[object, Any]", raw)
    return {str(key): value for key, value in metadata.items()}


@dataclasses.dataclass(frozen=True)
class RagHit:
    id: str
    content: str
    metadata: dict[str, Any]
    similarity: float
    passed_threshold: bool
    created_at: str | None


def _hit_from_row(row: Any, threshold: float) -> RagHit:
    raw_metadata: object = row.metadata
    created_at: object = row.createdAt
    similarity = float(row.sim)
    return RagHit(
        id=str(row.id),
        content=str(row.content),
        metadata=_metadata_dict(raw_metadata),
        similarity=similarity,
        passed_threshold=similarity >= threshold,
        created_at=created_at.isoformat() if isinstance(created_at, datetime) else None,
    )


class RagRetriever:
    def __init__(
        self,
        embedder: Embedder,
        session_factory: Callable[[], AsyncSession],
        collection_id: str,
        top_k: int = 3,
        threshold: float = 0.7,
    ) -> None:
        self._embedder = embedder
        self._session_factory: Callable[[], AsyncSession] = session_factory
        self._collection_id = collection_id
        self._top_k = top_k
        self._threshold = threshold

    async def retrieve(  # noqa: ANN201
        self, query: str
    ) -> tuple[list[str], dict[str, float]]:
        """Return (relevant_chunks, metrics) for the query."""
        hits, metrics = await self.retrieve_hits(query)
        return [hit.content for hit in hits if hit.passed_threshold], metrics

    async def retrieve_hits(self, query: str) -> tuple[list[RagHit], dict[str, float]]:
        """Return ranked chunks with similarity scores for debugging/admin use."""
        t0 = time.perf_counter()
        vec = await self._embedder.embed_one(query)
        embed_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        session: AsyncSession = self._session_factory()
        async with session as db:
            rows = await db.execute(  # type: ignore[union-attr]
                text("""
                    SELECT id,
                           content,
                           metadata,
                           "createdAt",
                           1 - (embedding <=> CAST(:vec AS vector)) AS sim
                    FROM "KnowledgeChunk"
                    WHERE "collectionId" = :cid
                      AND embedding IS NOT NULL
                      AND (:model_id IS NULL OR metadata->>'modelId' = :model_id)
                    ORDER BY embedding <=> CAST(:vec AS vector)
                    LIMIT :k
                """),
                {
                    "vec": str(vec),
                    "cid": self._collection_id,
                    "k": self._top_k,
                    "model_id": self._embedder.model_name,
                },
            )
            results: list[Any] = list(rows.fetchall())
        db_ms = (time.perf_counter() - t1) * 1000

        hits = [_hit_from_row(r, self._threshold) for r in results]
        top_sim = float(results[0].sim) if results else 0.0
        hit_count = sum(1 for hit in hits if hit.passed_threshold)

        metrics: dict[str, float] = {
            "rag_hit_count": float(hit_count),
            "rag_top_sim": top_sim,
            "latency_rag_ms": embed_ms + db_ms,
            "latency_embed_ms": embed_ms,
            "latency_db_ms": db_ms,
        }
        logger.debug(
            "RAG: query_len=%d hits=%d top_sim=%.3f embed_ms=%.1f db_ms=%.1f",
            len(query),
            hit_count,
            top_sim,
            embed_ms,
            db_ms,
        )
        return hits, metrics

    @staticmethod
    def build_context_block(chunks: list[str]) -> str:
        if not chunks:
            return ""
        lines = ["參考資料："]
        for i, chunk in enumerate(chunks, 1):
            lines.append(f"{i}. {chunk}")
        lines.append("若以上資料無相關，正常回答即可。")
        return "\n".join(lines)
