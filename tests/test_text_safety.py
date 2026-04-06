"""Text sanitization tests."""

from __future__ import annotations

from taigi_flow.text_safety import sanitize_piper_text


def test_sanitize_piper_text_keeps_supported_taibun_alphabet():
    assert sanitize_piper_text("Li2 ho2--ah0！") == "li2 ho2--ah0"


def test_sanitize_piper_text_drops_bopomofo_and_unsupported_tokens():
    assert sanitize_piper_text("ㄎㄨㄞˊ1 kin1-a2-jit8 ❤️") == "kin1-a2-jit8"
