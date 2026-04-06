"""監控後台 API — FastAPI endpoints 供即時查看使用狀況。"""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI
from prometheus_client import REGISTRY, generate_latest

app = FastAPI(title="Taigi-Flow Dashboard", version="0.1.0")

# 存放活躍 session 資訊（由 agent 更新）
_active_sessions: dict[str, dict[str, Any]] = {}


def register_session(session_id: str, info: dict[str, Any]) -> None:
    _active_sessions[session_id] = {**info, "registered_at": time.time()}


def unregister_session(session_id: str) -> None:
    _active_sessions.pop(session_id, None)


def update_session(session_id: str, info: dict[str, Any]) -> None:
    if session_id in _active_sessions:
        _active_sessions[session_id].update(info)


@app.get("/api/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    return [
        {"session_id": sid, **info} for sid, info in _active_sessions.items()
    ]


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    if session_id not in _active_sessions:
        return {"error": "session not found"}
    return {"session_id": session_id, **_active_sessions[session_id]}


@app.get("/metrics")
async def prometheus_metrics() -> bytes:
    return generate_latest(REGISTRY)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
