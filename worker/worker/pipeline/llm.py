import asyncio
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

FIRST_TOKEN_TIMEOUT = 5.0


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

        stream: Any = await asyncio.wait_for(
            self._client.chat.completions.create(**kwargs),  # type: ignore[arg-type]
            timeout=FIRST_TOKEN_TIMEOUT,
        )

        async def _gen() -> AsyncIterator[str]:
            async with asyncio.timeout(timeout):
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    if isinstance(content, str):
                        yield content

        return _gen()
