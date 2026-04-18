import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from worker.db.models import AgentProfile, InteractionLog, Session


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


class InteractionLogRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._factory() as session:
            yield session

    async def create_session(
        self,
        agent_profile_id: str,
        livekit_room: str,
    ) -> str:
        session_id = str(uuid.uuid4())
        async with self._session() as db:
            db.add(
                Session(
                    id=session_id,
                    agentProfileId=agent_profile_id,
                    livekitRoom=livekit_room,
                )
            )
            await db.commit()
        return session_id

    async def log_turn(
        self,
        session_id: str,
        turn_index: int,
        user_asr_text: str,
        llm_raw_text: str,
        hanlo_text: str | None,
        taibun_text: str,
        latencies: dict[str, int] | None = None,
        was_barged_in: bool = False,
        error_flag: str | None = None,
    ) -> None:
        lat = latencies or {}
        async with self._session() as db:
            db.add(
                InteractionLog(
                    id=str(uuid.uuid4()),
                    sessionId=session_id,
                    turnIndex=turn_index,
                    userAsrText=user_asr_text,
                    llmRawText=llm_raw_text,
                    hanloText=hanlo_text,
                    taibunText=taibun_text,
                    latencyAsrEnd=lat.get("asr_end"),
                    latencyLlmFirstTok=lat.get("llm_first_tok"),
                    latencyFirstAudio=lat.get("first_audio"),
                    latencyTotal=lat.get("total"),
                    wasBargedIn=was_barged_in,
                    errorFlag=error_flag,
                )
            )
            await db.commit()

    async def end_session(self, session_id: str) -> None:
        async with self._session() as db:
            await db.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(endedAt=func.now())
            )
            await db.commit()
