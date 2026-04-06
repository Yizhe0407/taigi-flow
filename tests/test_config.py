"""Settings tests."""

from __future__ import annotations

from taigi_flow.config import Settings


def test_settings_load_prompt_defaults_from_files():
    settings = Settings()

    assert "只輸出自然、口語、可朗讀的繁體中文" in settings.agent_instructions
    assert "一句簡短的繁體中文打招呼" in settings.agent_greeting_instructions
    assert settings.agent_allow_interruptions is True
    assert settings.agent_interruption_min_duration == 0.6
    assert settings.agent_aec_warmup_duration == 1.0
    assert settings.agent_tts_min_chars_per_chunk == 24
    assert settings.agent_tts_max_sentences_per_chunk == 2
