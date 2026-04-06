"""Startup bootstrap tests."""

from __future__ import annotations

import os
from pathlib import Path

from taigi_flow.bootstrap import load_env_file


def test_load_env_file_sets_missing_values(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "LIVEKIT_URL=ws://localhost:7880",
                "PIPER_VOICE='taigi'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    monkeypatch.delenv("PIPER_VOICE", raising=False)

    load_env_file(env_file)

    assert os.environ["LIVEKIT_URL"] == "ws://localhost:7880"
    assert os.environ["PIPER_VOICE"] == "taigi"


def test_load_env_file_does_not_override_existing_values(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env.local"
    env_file.write_text("LIVEKIT_URL=ws://from-file:7880\n", encoding="utf-8")
    monkeypatch.setenv("LIVEKIT_URL", "ws://from-env:7880")

    load_env_file(env_file)

    assert os.environ["LIVEKIT_URL"] == "ws://from-env:7880"
