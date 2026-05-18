"""Polls IngestJob table and processes pending jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, select, update

from worker.db.models import IngestJob, KnowledgeChunk
from worker.db.session import async_session_factory
from worker.ingest.chunker import chunk_file

if TYPE_CHECKING:
    from worker.ingest.embedder import Embedder

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5.0
_MAX_RETRY = 3
_STALE_THRESHOLD = timedelta(minutes=5)


class IngestRunner:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    async def run_forever(self) -> None:
        logger.info("IngestRunner started, polling every %.0fs", _POLL_INTERVAL)
        while True:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error("IngestRunner poll error: %s", e)
            await asyncio.sleep(_POLL_INTERVAL)

    async def _poll_once(self) -> None:
        async with async_session_factory() as session:
            # Recover jobs stuck in "processing" for longer than the stale threshold.
            # updatedAt is set when status changes to "processing", so it serves as
            # a processing-started timestamp.
            stale_cutoff = datetime.now(UTC).replace(tzinfo=None) - _STALE_THRESHOLD
            stale_result = await session.execute(
                update(IngestJob)
                .where(
                    and_(
                        IngestJob.status == "processing",
                        IngestJob.updatedAt < stale_cutoff,
                    )
                )
                .values(status="pending")
                .returning(IngestJob.id)
            )
            stale_ids = stale_result.scalars().all()
            if stale_ids:
                logger.warning(
                    "Reset %d stale processing job(s) to pending: %s",
                    len(stale_ids),
                    stale_ids,
                )

            result = await session.execute(
                select(IngestJob)
                .where(IngestJob.status == "pending")
                .order_by(IngestJob.createdAt)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = result.scalar_one_or_none()
            if job is None:
                await session.commit()
                return

            await session.execute(
                update(IngestJob)
                .where(IngestJob.id == job.id)
                .values(status="processing")
            )
            await session.commit()

        await self._process(job)

    async def _process(self, job: IngestJob) -> None:
        logger.info(
            "Processing IngestJob %s file=%s collection=%s",
            job.id,
            job.fileName,
            job.collectionId,
        )
        attempt = 0
        while attempt < _MAX_RETRY:
            attempt += 1
            try:
                chunks = await asyncio.get_event_loop().run_in_executor(
                    None, chunk_file, job.filePath
                )
                logger.info(
                    "Job %s: %d chunks from %s", job.id, len(chunks), job.fileName
                )

                texts = [c.content for c in chunks]
                embeddings = await self._embedder.embed_batch(texts)

                async with async_session_factory() as session:
                    # Guard: admin may delete the job while we embed, or stale
                    # recovery may have reset it to pending and another worker
                    # may have picked it up already.
                    still_exists = await session.get(IngestJob, job.id)
                    if still_exists is None:
                        logger.warning(
                            "Job %s deleted during processing, discarding chunks",
                            job.id,
                        )
                        return
                    if still_exists.status != "processing":
                        logger.warning(
                            "Job %s status changed to %s during embedding "
                            "(stale reset + re-pickup?), discarding to avoid dups",
                            job.id,
                            still_exists.status,
                        )
                        return
                    for chunk, vec in zip(chunks, embeddings, strict=True):
                        session.add(
                            KnowledgeChunk(
                                id=str(uuid.uuid4()),
                                collectionId=job.collectionId,
                                content=chunk.content,
                                doc_metadata={
                                    **chunk.metadata,
                                    "jobId": job.id,
                                    "modelId": self._embedder.model_name,
                                },
                                embedding=vec,
                            )
                        )
                    await session.execute(
                        update(IngestJob)
                        .where(IngestJob.id == job.id)
                        .values(status="done", chunkCount=len(chunks), error=None)
                    )
                    await session.commit()

                logger.info("Job %s done: %d chunks written", job.id, len(chunks))
                return

            except Exception as e:
                logger.warning(
                    "Job %s attempt %d/%d failed: %s",
                    job.id,
                    attempt,
                    _MAX_RETRY,
                    e,
                )
                if attempt >= _MAX_RETRY:
                    async with async_session_factory() as session:
                        await session.execute(
                            update(IngestJob)
                            .where(IngestJob.id == job.id)
                            .values(status="failed", error=str(e))
                        )
                        await session.commit()
                    logger.error("Job %s failed permanently: %s", job.id, e)
                    return
                await asyncio.sleep(2**attempt)
