"""Text safety helpers for the Taigi TTS pipeline."""

from __future__ import annotations

import re
import unicodedata

_ALLOWED_PIPER_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz -_012345678")
_LETTER_RE = re.compile(r"[a-z]")


def sanitize_piper_text(text: str) -> str:
    """Keep only characters supported by the local Taigi Piper voice.

    The bundled ``taigi_epoch1339`` voice is a direct text-token model whose
    alphabet is limited to ASCII letters, tone digits, spaces, ``-`` and ``_``.
    Any other characters are converted to spaces and then dropped if the token no
    longer contains alphabetic content.
    """

    normalized = unicodedata.normalize("NFKC", text).lower()
    cleaned = "".join(
        ch if ch in _ALLOWED_PIPER_CHARS else " "
        for ch in normalized
    )
    tokens = []
    for token in cleaned.split():
        if _LETTER_RE.search(token):
            tokens.append(token)
    return " ".join(tokens)
