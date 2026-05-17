"""HTTP server for admin RAG retrieval testing.

Run with:
    uv run python -m worker.rag_server
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, cast

from aiohttp import web
from dotenv import load_dotenv

from worker.db.session import async_session_factory
from worker.ingest.embedder import Embedder
from worker.pipeline.rag import RagRetriever

logger = logging.getLogger("worker.rag_server")


def _json_error(message: str, status: int) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _number(
    value: Any,
    *,
    default: float,
    min_value: float,
    max_value: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _integer(
    value: Any,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def query(request: web.Request) -> web.Response:
    try:
        raw_body: object = await request.json()
    except Exception:
        return _json_error("Invalid JSON body", 400)

    if not isinstance(raw_body, dict):
        return _json_error("JSON body must be an object", 400)

    raw_body_dict = cast("dict[object, object]", raw_body)
    body = {str(key): value for key, value in raw_body_dict.items()}
    raw_query = body.get("query")
    raw_collection_id = body.get("collectionId")
    if not isinstance(raw_query, str) or not raw_query.strip():
        return _json_error("query is required", 400)
    if not isinstance(raw_collection_id, str) or not raw_collection_id.strip():
        return _json_error("collectionId is required", 400)

    query_text = raw_query.strip()
    collection_id = raw_collection_id.strip()
    top_k = _integer(body.get("topK"), default=3, min_value=1, max_value=20)
    threshold = _number(
        body.get("threshold"), default=0.7, min_value=0.0, max_value=1.0
    )

    embedder = request.app["embedder"]
    assert isinstance(embedder, Embedder)

    retriever = RagRetriever(
        embedder=embedder,
        session_factory=async_session_factory,
        collection_id=collection_id,
        top_k=top_k,
        threshold=threshold,
    )
    hits, metrics = await retriever.retrieve_hits(query_text)

    return web.json_response(
        {
            "collectionId": collection_id,
            "query": query_text,
            "topK": top_k,
            "threshold": threshold,
            "metrics": {
                "hitCount": int(metrics["rag_hit_count"]),
                "topSimilarity": metrics["rag_top_sim"],
                "latencyMs": metrics["latency_rag_ms"],
                "embeddingMs": metrics["latency_embed_ms"],
                "dbMs": metrics["latency_db_ms"],
            },
            "results": [
                {
                    "id": hit.id,
                    "content": hit.content,
                    "metadata": hit.metadata,
                    "similarity": hit.similarity,
                    "passedThreshold": hit.passed_threshold,
                    "createdAt": hit.created_at,
                }
                for hit in hits
            ],
        }
    )


async def create_app() -> web.Application:
    logging.info("Loading embedding model for RAG retrieval server...")
    embedder = Embedder()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, embedder.load)

    app = web.Application()
    app["embedder"] = embedder
    app.router.add_get("/healthz", health)
    app.router.add_post("/rag/query", query)
    return app


def main() -> None:
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    host = os.getenv("RAG_SERVER_HOST", "127.0.0.1")
    port = _integer(
        os.getenv("RAG_SERVER_PORT"), default=8765, min_value=1, max_value=65535
    )
    logger.info("Starting RAG retrieval server on http://%s:%d", host, port)
    web.run_app(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
