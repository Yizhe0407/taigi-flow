import asyncio
import json

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

from worker.pipeline.llm import FIRST_TOKEN_TIMEOUT, LLMClient


def _sse_response(tokens: list[str], model: str = "test") -> str:
    lines: list[str] = []
    for tok in tokens:
        chunk = {
            "choices": [{"delta": {"content": tok}, "finish_reason": None}],
        }
        lines.append(f"data: {json.dumps(chunk)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines)


def _make_client(httpserver: HTTPServer) -> LLMClient:
    return LLMClient(
        base_url=httpserver.url_for("/v1"),
        api_key="test",
        model="test-model",
    )


@pytest.mark.asyncio
async def test_basic_stream(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v1/chat/completions").respond_with_data(
        _sse_response(["Hello", ", ", "world", "!"]),
        content_type="text/event-stream",
    )
    client = _make_client(httpserver)
    messages = [{"role": "user", "content": "hi"}]
    tokens: list[str] = []
    async for tok in await client.stream(messages):
        tokens.append(tok)
    assert "".join(tokens) == "Hello, world!"


@pytest.mark.asyncio
async def test_timeout_on_connect(httpserver: HTTPServer) -> None:
    def slow_handler(request: Request) -> Response:
        import time

        time.sleep(FIRST_TOKEN_TIMEOUT + 1)
        return Response(_sse_response(["hi"]), content_type="text/event-stream")

    httpserver.expect_request("/v1/chat/completions").respond_with_handler(slow_handler)
    client = _make_client(httpserver)
    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        await client.stream([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_cancellation(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v1/chat/completions").respond_with_data(
        _sse_response(["a", "b", "c"]),
        content_type="text/event-stream",
    )
    client = _make_client(httpserver)
    task = asyncio.create_task(_consume(client))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def _consume(client: LLMClient) -> list[str]:
    tokens: list[str] = []
    async for tok in await client.stream([{"role": "user", "content": "go"}]):
        tokens.append(tok)
        await asyncio.sleep(0.1)
    return tokens


@pytest.mark.asyncio
async def test_empty_content_chunks_filtered(httpserver: HTTPServer) -> None:
    raw_chunks = [
        {"choices": [{"delta": {"content": None}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    body = (
        "".join(f"data: {json.dumps(c)}\n\n" for c in raw_chunks)
        + "data: [DONE]\n\n"
    )
    httpserver.expect_request("/v1/chat/completions").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = _make_client(httpserver)
    tokens: list[str] = []
    async for tok in await client.stream([{"role": "user", "content": "hi"}]):
        tokens.append(tok)
    assert tokens == ["hi"]
