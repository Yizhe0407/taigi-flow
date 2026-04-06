"""Ollama LLM wrapper for LiveKit.

LiveKit's OpenAI-compatible plugin applies its own 10-second request timeout
through APIConnectOptions on every chat call. Ollama model cold-start often
exceeds that, so we override the default connection options for this backend.
"""

from __future__ import annotations

from typing import Any

import httpx
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions, llm
from livekit.agents.llm import ToolChoice, utils as llm_utils
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.plugins import openai
from openai.types.chat import completion_create_params


class OllamaLLM(openai.LLM):
    """OpenAI-compatible Ollama client with a longer default chat timeout."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        request_timeout_seconds: float,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            api_key="ollama",
            timeout=httpx.Timeout(request_timeout_seconds, connect=15.0),
        )
        self._default_conn_options = APIConnectOptions(
            max_retry=DEFAULT_API_CONNECT_OPTIONS.max_retry,
            retry_interval=DEFAULT_API_CONNECT_OPTIONS.retry_interval,
            timeout=request_timeout_seconds,
        )

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        response_format: NotGivenOr[
            completion_create_params.ResponseFormat | type[llm_utils.ResponseFormatT]
        ] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> openai.LLMStream:
        if conn_options is DEFAULT_API_CONNECT_OPTIONS:
            conn_options = self._default_conn_options

        return super().chat(
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
            parallel_tool_calls=parallel_tool_calls,
            tool_choice=tool_choice,
            response_format=response_format,
            extra_kwargs=extra_kwargs,
        )
