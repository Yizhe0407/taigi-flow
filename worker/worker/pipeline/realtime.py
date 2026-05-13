"""Redis pub/sub publisher for real-time monitor events.

Events are published to the 'taigi:live' channel as JSON. The admin SSE
endpoint subscribes to this channel and forwards events to connected browsers.

All publish calls are fire-and-forget (errors only log a warning) so Redis
failure can never crash the voice pipeline.
"""

import json
import logging
import os
import time
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger("worker.pipeline.realtime")
CHANNEL = "taigi:live"


class RealtimePublisher:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def _get(self) -> aioredis.Redis:
        if self._redis is None:
            url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self._redis = aioredis.from_url(url, decode_responses=True)
        return self._redis

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        try:
            r = await self._get()
            payload = json.dumps({"type": event_type, "ts": time.time(), **data})
            await r.publish(CHANNEL, payload)  # type: ignore[misc]
        except Exception as e:
            logger.warning("realtime publish failed (%s): %s", event_type, e)

    async def asr_done(self, session_id: str, agent_name: str, text: str) -> None:
        await self.publish("asr", {
            "sessionId": session_id,
            "agentName": agent_name,
            "text": text,
        })

    async def llm_sentence(
        self, session_id: str, sentence: str, hanlo: str, taibun: str
    ) -> None:
        await self.publish("llm_sentence", {
            "sessionId": session_id,
            "sentence": sentence,
            "hanlo": hanlo,
            "taibun": taibun,
        })

    async def tts_first_audio(
        self, session_id: str, latency_ms: float
    ) -> None:
        await self.publish("tts_first_audio", {
            "sessionId": session_id,
            "latencyMs": round(latency_ms),
        })

    async def turn_done(
        self,
        session_id: str,
        full_response: str,
        latency_asr_ms: float | None,
        latency_llm_first_tok_ms: float | None,
        latency_first_audio_ms: float | None,
        was_barged_in: bool,
        error_flag: str | None,
    ) -> None:
        await self.publish("turn_done", {
            "sessionId": session_id,
            "fullResponse": full_response,
            "latencyAsrMs": round(latency_asr_ms) if latency_asr_ms else None,
            "latencyLlmFirstTokMs": (
                round(latency_llm_first_tok_ms) if latency_llm_first_tok_ms else None
            ),
            "latencyFirstAudioMs": (
                round(latency_first_audio_ms) if latency_first_audio_ms else None
            ),
            "wasBargedIn": was_barged_in,
            "errorFlag": error_flag,
        })

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None
