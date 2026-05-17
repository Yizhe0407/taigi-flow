from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from worker.ingest.embedder import Embedder

logger = logging.getLogger(__name__)


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
        t0 = time.perf_counter()
        vec = await self._embedder.embed_one(query)
        embed_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        session: AsyncSession = self._session_factory()
        async with session as db:
            rows = await db.execute(  # type: ignore[union-attr]
                text("""
                    SELECT content,
                           1 - (embedding <=> CAST(:vec AS vector)) AS sim
                    FROM "KnowledgeChunk"
                    WHERE "collectionId" = :cid
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:vec AS vector)
                    LIMIT :k
                """),
                {
                    "vec": str(vec),
                    "cid": self._collection_id,
                    "k": self._top_k,
                },
            )
            results: list[Any] = list(rows.fetchall())
        db_ms = (time.perf_counter() - t1) * 1000

        hits = [r.content for r in results if float(r.sim) >= self._threshold]
        top_sim = float(results[0].sim) if results else 0.0

        metrics: dict[str, float] = {
            "rag_hit_count": float(len(hits)),
            "rag_top_sim": top_sim,
            "latency_rag_ms": embed_ms + db_ms,
        }
        logger.debug(
            "RAG: query_len=%d hits=%d top_sim=%.3f embed_ms=%.1f db_ms=%.1f",
            len(query),
            len(hits),
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
