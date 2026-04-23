import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_factory: async_sessionmaker[AsyncSession] | None = None


def _get_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL environment variable is not set")
        engine = create_async_engine(
            url.replace("postgresql://", "postgresql+asyncpg://"),
            echo=False,
        )
        _factory = async_sessionmaker(engine, expire_on_commit=False)
    return _factory


def async_session_factory() -> AsyncSession:
    return _get_factory()()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _get_factory()() as session:
        yield session
