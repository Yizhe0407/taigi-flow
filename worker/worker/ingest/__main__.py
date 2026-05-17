"""Entry point: uv run python -m worker.ingest"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv

from worker.ingest.embedder import Embedder
from worker.ingest.runner import IngestRunner

_env = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
load_dotenv(dotenv_path=_env)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)


async def main() -> None:
    logging.info("Starting ingest worker …")
    embedder = Embedder()
    logging.info(
        "Loading embedding model (first run downloads ~1.2 GB, please wait) …"
    )
    embedder.load()
    runner = IngestRunner(embedder)
    await runner.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
