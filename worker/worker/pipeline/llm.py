import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from ..tools.base import BaseTool

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
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        kwargs: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

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

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list["BaseTool"],
        max_rounds: int = 3,
        timeout: float = 15.0,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        from ..tools import TOOL_REGISTRY

        msgs: list[dict[str, Any]] = list(messages)
        tool_schemas = [t.to_openai_schema() for t in tools]

        async def _gen() -> AsyncIterator[str]:
            for _round in range(max_rounds):
                tool_calls_buffer: dict[int, dict[str, str]] = {}

                create_kwargs: dict[str, Any] = {
                    "model": self._model,
                    "messages": msgs,
                    "tools": tool_schemas,
                    "stream": True,
                }
                if max_tokens is not None:
                    create_kwargs["max_tokens"] = max_tokens

                try:
                    stream: Any = await asyncio.wait_for(
                        self._client.chat.completions.create(**create_kwargs),  # type: ignore[arg-type]
                        timeout=FIRST_TOKEN_TIMEOUT,
                    )
                except TimeoutError as e:
                    raise TimeoutError(
                        f"LLM first token timeout after {FIRST_TOKEN_TIMEOUT:.1f}s"
                    ) from e

                aiter = stream.__aiter__()
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            aiter.__anext__(), timeout=timeout
                        )
                    except StopAsyncIteration:
                        break
                    except TimeoutError as e:
                        raise TimeoutError(
                            f"LLM inter-token timeout after {timeout:.1f}s"
                        ) from e

                    delta = chunk.choices[0].delta
                    if getattr(delta, "tool_calls", None):
                        for tc in delta.tool_calls:
                            buf = tool_calls_buffer.setdefault(
                                tc.index, {"id": "", "name": "", "args": ""}
                            )
                            if tc.id:
                                buf["id"] = tc.id
                            if tc.function and tc.function.name:
                                buf["name"] = tc.function.name
                            if tc.function and tc.function.arguments:
                                buf["args"] += tc.function.arguments
                    elif isinstance(getattr(delta, "content", None), str):
                        yield delta.content  # type: ignore[misc]

                if not tool_calls_buffer:
                    return

                # Build assistant message with tool_calls
                assistant_tool_calls = [
                    {
                        "id": buf["id"],
                        "type": "function",
                        "function": {
                            "name": buf["name"],
                            "arguments": buf["args"],
                        },
                    }
                    for buf in tool_calls_buffer.values()
                ]
                msgs.append(
                    {"role": "assistant", "tool_calls": assistant_tool_calls}
                )

                # Execute each tool call
                for buf in tool_calls_buffer.values():
                    from ..tools import API_NAME_MAP
                    internal_name = API_NAME_MAP.get(buf["name"], buf["name"])
                    tool = TOOL_REGISTRY.get(internal_name)
                    t_start = asyncio.get_event_loop().time()
                    try:
                        args: dict[str, Any] = (
                            json.loads(buf["args"]) if buf["args"] else {}
                        )
                        if tool is None:
                            result = f"Unknown tool: {buf['name']}"
                        else:
                            result = await tool.execute(**args)
                    except Exception as exc:
                        result = f"Tool error: {exc}"
                        logger.warning(
                            "tool_call name=%s error=%s", buf["name"], exc
                        )
                    latency_ms = (asyncio.get_event_loop().time() - t_start) * 1000
                    logger.info(
                        "tool_call_completed name=%s latency_tool_ms=%.1f",
                        buf["name"],
                        latency_ms,
                    )
                    msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": buf["id"],
                            "content": result,
                        }
                    )

            # Every round had tool calls — yield fallback so runner logs an error flag.
            logger.warning(
                "stream_with_tools: exhausted max_rounds=%d without text response",
                max_rounds,
            )
            yield "（工具呼叫次數超過上限，無法產生回覆）"

        return _gen()
