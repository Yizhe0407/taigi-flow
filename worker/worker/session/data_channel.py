"""LiveKit data channel publisher for map/UI events, and client location store."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from livekit import rtc

logger = logging.getLogger(__name__)

_participant: rtc.LocalParticipant | None = None
_client_location: dict[str, float] | None = None  # {lat, lng}


def set_participant(participant: rtc.LocalParticipant) -> None:
    global _participant
    _participant = participant


def set_client_location(lat: float, lng: float) -> None:
    global _client_location
    _client_location = {"lat": lat, "lng": lng}
    logger.info("Client location updated: lat=%.5f lng=%.5f", lat, lng)


def get_client_location() -> dict[str, float] | None:
    return _client_location


async def _publish(topic: str, payload: dict[str, Any]) -> None:
    if _participant is None:
        return
    try:
        data = json.dumps(payload, ensure_ascii=False).encode()
        await _participant.publish_data(data, reliable=True, topic=topic)
    except Exception as exc:
        logger.warning("data channel publish failed (topic=%s): %s", topic, exc)


async def publish_map_event(payload: dict[str, Any]) -> None:
    await _publish("map", payload)


async def publish_conv_event(payload: dict[str, Any]) -> None:
    await _publish("conv", payload)
