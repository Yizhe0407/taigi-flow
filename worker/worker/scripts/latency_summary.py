"""Latency and error summary for a recorded voice session.

Usage:
    uv run python -m worker.scripts.latency_summary --session <id>
    uv run python -m worker.scripts.latency_summary --list
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
from collections import Counter
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from sqlalchemy import select

from worker.db.models import InteractionLog, Session
from worker.db.session import async_session_factory

if TYPE_CHECKING:
    from datetime import datetime

_ENV = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
load_dotenv(dotenv_path=_ENV)


def _pct(values: list[int], p: float) -> int:
    if not values:
        return 0
    idx = max(0, int(len(values) * p / 100) - 1)
    return sorted(values)[idx]


def _fmt_ms(ms: float) -> str:
    return f"{int(ms)}ms"


def _fmt_duration(start: datetime, end: datetime) -> str:
    total_s = int((end - start).total_seconds())
    m, s = divmod(total_s, 60)
    return f"{m}m {s:02d}s"


def _stats_line(label: str, values: list[int]) -> str:
    if not values:
        return f"  {label:<22} (no data)"
    avg = statistics.mean(values)
    p50 = _pct(values, 50)
    p95 = _pct(values, 95)
    mx = max(values)
    parts = (
        f"avg={_fmt_ms(avg)}  p50={_fmt_ms(p50)}  p95={_fmt_ms(p95)}  max={_fmt_ms(mx)}"
    )
    return f"  {label:<22} {parts}"


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


async def _resolve_session(db_session: object, prefix: str) -> Session | None:
    """Accept full UUID or unique prefix."""
    from sqlalchemy.ext.asyncio import AsyncSession as _AS

    assert isinstance(db_session, _AS)
    if len(prefix) == 36:
        result = await db_session.execute(select(Session).where(Session.id == prefix))
        return result.scalar_one_or_none()
    result = await db_session.execute(
        select(Session).where(Session.id.like(f"{prefix}%"))
    )
    rows = list(result.scalars())
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        print(
            f"Ambiguous prefix '{prefix}' matches {len(rows)} sessions. Use more chars."
        )
        return None
    return None


async def _run_summary(session_id: str) -> None:
    async with async_session_factory() as db:
        sess = await _resolve_session(db, session_id)
        if sess is None:
            print(f"Session not found: {session_id}")
            return
        full_id = sess.id

        logs_result = await db.execute(
            select(InteractionLog)
            .where(InteractionLog.sessionId == full_id)
            .order_by(InteractionLog.turnIndex)
        )
        logs: list[InteractionLog] = list(logs_result.scalars())

    if not logs:
        print(f"Session {full_id} has no interaction logs.")
        return

    turns = len(logs)
    start = _naive(sess.startedAt)
    end = _naive(sess.endedAt) if sess.endedAt else _naive(logs[-1].createdAt)
    duration = _fmt_duration(start, end)

    asr_end = [row.latencyAsrEnd for row in logs if row.latencyAsrEnd is not None]
    llm_first = [
        row.latencyLlmFirstTok for row in logs if row.latencyLlmFirstTok is not None
    ]
    first_audio = [
        row.latencyFirstAudio for row in logs if row.latencyFirstAudio is not None
    ]
    total = [row.latencyTotal for row in logs if row.latencyTotal is not None]

    errors = [row.errorFlag for row in logs if row.errorFlag is not None]
    error_counts: Counter[str] = Counter(errors)
    error_rate = len(errors) / turns * 100 if turns else 0.0

    print(f"\nSession: {full_id}   Turns: {turns}   Duration: {duration}")
    print()
    print(_stats_line("latency_total", total))
    print(_stats_line("latency_asr_end", asr_end))
    print(_stats_line("latency_llm_first", llm_first))
    print(_stats_line("latency_first_audio", first_audio))
    print()
    print(f"  Errors: {len(errors)}/{turns} ({error_rate:.1f}%)")
    for flag, count in error_counts.most_common():
        print(f"    - {flag}: {count}")
    if not errors:
        print("    (none)")
    print()


async def _list_sessions(limit: int = 10) -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Session).order_by(Session.startedAt.desc()).limit(limit)
        )
        sessions: list[Session] = list(result.scalars())

    if not sessions:
        print("No sessions found.")
        return

    hdr = f"  {'ID':<36}  {'Room':<25}  {'Started':<21} Ended"
    print(f"\n{hdr}")
    print("  " + "-" * 90)
    for s in sessions:
        started = s.startedAt.strftime("%Y-%m-%d %H:%M:%S")
        ended = s.endedAt.strftime("%H:%M:%S") if s.endedAt else "ongoing"
        print(f"  {s.id:<36}  {s.livekitRoom:<25}  {started}  {ended}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency summary for a voice session")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session", metavar="ID", help="Session UUID to summarize")
    group.add_argument("--list", action="store_true", help="List recent sessions")
    parser.add_argument(
        "--limit", type=int, default=10, help="--list row limit (default 10)"
    )
    args = parser.parse_args()

    if args.list:
        asyncio.run(_list_sessions(args.limit))
    else:
        asyncio.run(_run_summary(args.session))


if __name__ == "__main__":
    main()
