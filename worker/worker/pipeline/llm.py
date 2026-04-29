import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def parse_first_token_timeout(raw: str | None, default: float = 5.0) -> float:
    if raw is None:
        return default
    try:
        timeout = float(raw)
    except ValueError:
        logger.warning(
            "Invalid LLM_FIRST_TOKEN_TIMEOUT=%s, fallback to %.1fs",
            raw,
            default,
        )
        return default
    if timeout <= 0:
        logger.warning(
            "Non-positive LLM_FIRST_TOKEN_TIMEOUT=%s, fallback to %.1fs",
            raw,
            default,
        )
        return default
    return timeout


FIRST_TOKEN_TIMEOUT = parse_first_token_timeout(os.getenv("LLM_FIRST_TOKEN_TIMEOUT"))


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def stream(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, object]] | None = None,
        timeout: float = 15.0,
    ) -> AsyncIterator[str]:
        kwargs: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            stream: Any = await asyncio.wait_for(
                self._client.chat.completions.create(**kwargs),  # type: ignore[arg-type]
                timeout=FIRST_TOKEN_TIMEOUT,
            )
        except TimeoutError as e:
            raise TimeoutError(
                f"LLM first token timeout after {FIRST_TOKEN_TIMEOUT:.1f}s"
            ) from e

        async def _gen() -> AsyncIterator[str]:
            # Apply timeout per-token, not as a total deadline.
            # A wall-clock timeout wrapping the whole generator counts TTS time
            # (awaited between yields by the caller) against the budget, which
            # causes spurious timeouts on long responses.
            aiter = stream.__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(aiter.__anext__(), timeout=timeout)
                except StopAsyncIteration:
                    break
                except TimeoutError as e:
                    raise TimeoutError(
                        f"LLM inter-token timeout after {timeout:.1f}s"
                    ) from e
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if isinstance(content, str):
                    yield content

        return _gen()
