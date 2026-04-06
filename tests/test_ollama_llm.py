"""Ollama LLM wrapper tests."""

from __future__ import annotations

from unittest.mock import patch, sentinel

from livekit.agents import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS, llm

from taigi_flow.llm import OllamaLLM


def test_chat_replaces_livekit_default_conn_timeout():
    model = OllamaLLM(
        base_url="http://localhost:11434/v1",
        model="frob/qwen3.5-instruct:4b",
        request_timeout_seconds=90.0,
    )

    with patch("taigi_flow.llm.ollama.openai.LLM.chat", return_value=sentinel.stream) as base_chat:
        result = model.chat(chat_ctx=llm.ChatContext())

    assert result is sentinel.stream
    conn_options = base_chat.call_args.kwargs["conn_options"]
    assert conn_options.timeout == 90.0
    assert conn_options.max_retry == DEFAULT_API_CONNECT_OPTIONS.max_retry
    assert conn_options.retry_interval == DEFAULT_API_CONNECT_OPTIONS.retry_interval


def test_chat_preserves_explicit_conn_options():
    model = OllamaLLM(
        base_url="http://localhost:11434/v1",
        model="frob/qwen3.5-instruct:4b",
        request_timeout_seconds=90.0,
    )
    explicit_conn_options = APIConnectOptions(timeout=12.0, max_retry=1, retry_interval=0.5)

    with patch("taigi_flow.llm.ollama.openai.LLM.chat", return_value=sentinel.stream) as base_chat:
        model.chat(chat_ctx=llm.ChatContext(), conn_options=explicit_conn_options)

    assert base_chat.call_args.kwargs["conn_options"] is explicit_conn_options
