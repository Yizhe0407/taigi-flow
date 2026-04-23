import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from worker.db.models import AgentProfile, InteractionLog, Session
from worker.db.repositories import InteractionLogRepository
from worker.db.time import now_utc

_DB_URL = os.environ.get("DATABASE_URL", "")
_ASYNC_URL = (
    _DB_URL.replace("postgresql://", "postgresql+asyncpg://") if _DB_URL else ""
)

pytestmark = pytest.mark.skipif(
    not _DB_URL, reason="DATABASE_URL not set — skipping DB integration tests"
)


@pytest.fixture
async def repo_bundle() -> tuple[
    InteractionLogRepository, async_sessionmaker[AsyncSession]
]:
    engine = create_async_engine(_ASYNC_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # ensure a test AgentProfile exists
    async with factory() as db:
        existing = await db.get(AgentProfile, "test-profile-p1")
        if existing is None:
            now = now_utc()
            db.add(
                AgentProfile(
                    id="test-profile-p1",
                    name="P1 Test Profile",
                    systemPrompt="Test.",
                    voiceConfig={},
                    tools=[],
                    createdAt=now,
                    updatedAt=now,
                )
            )
            await db.commit()

    return InteractionLogRepository(factory), factory


@pytest.mark.asyncio
async def test_create_session_returns_id(
    repo_bundle: tuple[InteractionLogRepository, async_sessionmaker[AsyncSession]],
) -> None:
    repo, _ = repo_bundle
    session_id = await repo.create_session("test-profile-p1", "room-test-001")
    assert isinstance(session_id, str)
    assert len(session_id) > 0


@pytest.mark.asyncio
async def test_log_turn_writes_to_db(
    repo_bundle: tuple[InteractionLogRepository, async_sessionmaker[AsyncSession]],
) -> None:
    repo, factory = repo_bundle
    session_id = await repo.create_session("test-profile-p1", "room-test-002")
    await repo.log_turn(
        session_id=session_id,
        turn_index=0,
        user_asr_text="你好",
        llm_raw_text="你好，有什麼可以幫你？",
        hanlo_text="你好，有啥物會當幫你？",
        taibun_text="Lí hó, ū siánn-mih ē-tàng pang lí?",
        latencies={"llm_first_tok": 342, "total": 1203},
    )
    async with factory() as db:
        result = await db.execute(
            select(InteractionLog).where(InteractionLog.sessionId == session_id)
        )
        logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].turnIndex == 0
    assert logs[0].userAsrText == "你好"
    assert logs[0].latencyLlmFirstTok == 342
    assert logs[0].latencyTotal == 1203
    assert logs[0].createdAt is not None


@pytest.mark.asyncio
async def test_multiple_turns_sequential_index(
    repo_bundle: tuple[InteractionLogRepository, async_sessionmaker[AsyncSession]],
) -> None:
    repo, factory = repo_bundle
    session_id = await repo.create_session("test-profile-p1", "room-test-003")
    for i in range(3):
        await repo.log_turn(
            session_id=session_id,
            turn_index=i,
            user_asr_text=f"u{i}",
            llm_raw_text=f"a{i}",
            hanlo_text=None,
            taibun_text=f"t{i}",
        )
    async with factory() as db:
        result = await db.execute(
            select(InteractionLog)
            .where(InteractionLog.sessionId == session_id)
            .order_by(InteractionLog.turnIndex)
        )
        logs = result.scalars().all()
    assert [log.turnIndex for log in logs] == [0, 1, 2]


@pytest.mark.asyncio
async def test_end_session_sets_ended_at(
    repo_bundle: tuple[InteractionLogRepository, async_sessionmaker[AsyncSession]],
) -> None:
    repo, factory = repo_bundle
    session_id = await repo.create_session("test-profile-p1", "room-test-004")
    await repo.end_session(session_id)
    async with factory() as db:
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one()
    assert session.endedAt is not None
