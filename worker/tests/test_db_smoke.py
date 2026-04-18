import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from worker.db.models import AgentProfile
from worker.db.repositories import AgentProfileRepository

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://admin:devpassword@localhost:5432/agent_system",
).replace("postgresql://", "postgresql+asyncpg://")


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:  # type: ignore[misc]
    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_db_connection(session: AsyncSession) -> None:
    result = await session.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_seed_agent_profile_exists(session: AsyncSession) -> None:
    result = await session.execute(
        select(AgentProfile).where(AgentProfile.name == "公車站長")
    )
    profile = result.scalar_one_or_none()
    assert profile is not None
    assert profile.isActive is True


async def test_repository_get_active_by_id(session: AsyncSession) -> None:
    result = await session.execute(
        select(AgentProfile).where(AgentProfile.name == "公車站長")
    )
    profile = result.scalar_one_or_none()
    assert profile is not None

    repo = AgentProfileRepository(session)
    fetched = await repo.get_active_by_id(profile.id)
    assert fetched is not None
    assert fetched.name == "公車站長"
