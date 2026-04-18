from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.db.models import AgentProfile


class AgentProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_id(self, profile_id: str) -> AgentProfile | None:
        result = await self._session.execute(
            select(AgentProfile).where(
                AgentProfile.id == profile_id,
                AgentProfile.isActive.is_(True),
            )
        )
        return result.scalar_one_or_none()
