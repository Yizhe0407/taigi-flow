"""Component factory tests."""

from __future__ import annotations

from unittest.mock import patch

from taigi_flow.config import Settings
from taigi_flow.factory import ComponentFactory


def test_create_llm_uses_ollama_wrapper_with_configured_timeout():
    settings = Settings(llm_timeout_seconds=90.0)

    with patch("taigi_flow.factory.OllamaLLM") as llm_cls:
        ComponentFactory.create_llm(settings)

    llm_cls.assert_called_once_with(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        request_timeout_seconds=90.0,
    )
