"""LiveKit data channel publisher for map/UI events, and client location store.

Single-session design: the project explicitly does not support concurrent
multi-user connections (see CLAUDE.md). A warning is logged if a second
session calls set_participant() while the first is still active.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from livekit import rtc

logger = logging.getLogger(__name__)


class _SessionState:
    def __init__(self) -> None:
        self.participant: rtc.LocalParticipant | None = None
        self.client_location: dict[str, float] | None = None


_state = _SessionState()


def reset_session() -> None:
    """Clear state from a previous session. Call at the start of each entrypoint."""
    _state.participant = None
    _state.client_location = None


def set_participant(participant: rtc.LocalParticipant) -> None:
    if _state.participant is not None and _state.participant is not participant:
        logger.warning(
            "set_participant called while a participant is already active — "
            "potential multi-session conflict; old participant replaced"
        )
    _state.participant = participant


def set_client_location(lat: float, lng: float) -> None:
    _state.client_location = {"lat": lat, "lng": lng}
    logger.info("Client location updated: lat=%.5f lng=%.5f", lat, lng)


def get_client_location() -> dict[str, float] | None:
    return _state.client_location


async def _publish(topic: str, payload: dict[str, Any]) -> None:
    if _state.participant is None:
        return
    try:
        data = json.dumps(payload, ensure_ascii=False).encode()
        await _state.participant.publish_data(data, reliable=True, topic=topic)
    except Exception as exc:
        logger.warning("data channel publish failed (topic=%s): %s", topic, exc)


async def publish_map_event(payload: dict[str, Any]) -> None:
    await _publish("map", payload)


async def publish_conv_event(payload: dict[str, Any]) -> None:
    await _publish("conv", payload)
