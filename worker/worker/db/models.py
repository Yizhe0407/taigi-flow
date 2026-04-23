from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from worker.db.time import now_utc


class Base(DeclarativeBase):
    pass


class AgentProfile(Base):
    __tablename__ = "AgentProfile"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    systemPrompt: Mapped[str] = mapped_column(Text, nullable=False)
    voiceConfig: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ragConfig: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    isActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=now_utc,
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=now_utc,
        onupdate=now_utc,
        nullable=False,
    )

    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="agentProfile"
    )


class Session(Base):
    __tablename__ = "Session"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    agentProfileId: Mapped[str] = mapped_column(
        String, ForeignKey("AgentProfile.id"), nullable=False
    )
    livekitRoom: Mapped[str] = mapped_column(String, nullable=False)
    startedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=now_utc,
        nullable=False,
    )
    endedAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    agentProfile: Mapped[AgentProfile] = relationship(
        "AgentProfile", back_populates="sessions"
    )
    logs: Mapped[list["InteractionLog"]] = relationship(
        "InteractionLog", back_populates="session"
    )


class InteractionLog(Base):
    __tablename__ = "InteractionLog"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sessionId: Mapped[str] = mapped_column(
        String, ForeignKey("Session.id"), nullable=False
    )
    turnIndex: Mapped[int] = mapped_column(Integer, nullable=False)

    userAsrText: Mapped[str] = mapped_column(Text, nullable=False)
    llmRawText: Mapped[str] = mapped_column(Text, nullable=False)
    hanloText: Mapped[str | None] = mapped_column(Text, nullable=True)
    taibunText: Mapped[str] = mapped_column(Text, nullable=False)

    latencyAsrEnd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latencyLlmFirstTok: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latencyFirstAudio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latencyTotal: Mapped[int | None] = mapped_column(Integer, nullable=True)

    wasBargedIn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    errorFlag: Mapped[str | None] = mapped_column(String, nullable=True)

    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=now_utc,
        nullable=False,
    )

    session: Mapped[Session] = relationship("Session", back_populates="logs")


class PronunciationEntry(Base):
    __tablename__ = "PronunciationEntry"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    profileId: Mapped[str | None] = mapped_column(String, nullable=True)
    term: Mapped[str] = mapped_column(String, nullable=False)
    replacement: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=now_utc,
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=now_utc,
        onupdate=now_utc,
        nullable=False,
    )
