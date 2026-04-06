"""LiveKit token helper tests."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from livekit.api import TokenVerifier

from taigi_flow.tools import livekit_token


class TestLivekitTokenTool:
    def test_generate_room_name_uses_prefix(self):
        room = livekit_token.generate_room_name("demo")
        assert room.startswith("demo-")
        assert len(room.split("-")) >= 4

    def test_create_participant_token_contains_room_and_identity(self):
        token = livekit_token.create_participant_token(
            api_key="devkey",
            api_secret="devsecretdevsecretdevsecret12",
            room="demo-room",
            identity="alice",
            ttl_minutes=30,
            name="Alice",
        )

        claims = TokenVerifier(
            api_key="devkey",
            api_secret="devsecretdevsecretdevsecret12",
        ).verify(token)

        assert claims.identity == "alice"
        assert claims.name == "Alice"
        assert claims.video is not None
        assert claims.video.room == "demo-room"
        assert claims.video.room_join is True

    def test_main_prints_json_output(self):
        buffer = StringIO()
        with (
            patch(
                "taigi_flow.tools.livekit_token.Settings",
                return_value=type(
                    "DummySettings",
                    (),
                    {
                        "livekit_api_key": "devkey",
                        "livekit_api_secret": "devsecretdevsecretdevsecret12",
                        "livekit_url": "ws://localhost:7880",
                    },
                )(),
            ),
            patch(
                "taigi_flow.tools.livekit_token.generate_room_name",
                return_value="demo-room",
            ),
            patch("sys.argv", ["taigi-room-token", "--json"]),
            redirect_stdout(buffer),
        ):
            livekit_token.main()

        payload = json.loads(buffer.getvalue())
        assert payload["livekit_url"] == "ws://localhost:7880"
        assert payload["room"] == "demo-room"
        assert payload["identity"] == "user1"
        assert payload["name"] == "user1"
        assert isinstance(payload["token"], str)
