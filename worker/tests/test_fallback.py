from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.audio.fallback import FALLBACK_TEXTS, FallbackPlayer


def _make_audio_source() -> MagicMock:
    src = MagicMock()
    src.capture_frame = AsyncMock()
    return src


def _make_text_processor(taibun: str = "fake-taibun") -> MagicMock:
    result = MagicMock()
    result.taibun = taibun
    proc = MagicMock()
    proc.process.return_value = result
    return proc


def _make_tts(pcm: bytes = b"\x00" * 640) -> MagicMock:
    """Returns a fake PiperTTS whose synthesize is an async generator yielding pcm."""

    async def _synth(_text: str):  # type: ignore[no-untyped-def]
        yield pcm

    tts = MagicMock()
    tts.synthesize = _synth
    return tts


@pytest.mark.asyncio
async def test_pregenerate_populates_all_five_kinds() -> None:
    player = FallbackPlayer(_make_audio_source())
    await player.pregenerate(_make_tts(), _make_text_processor())
    assert set(player._audios.keys()) == set(FALLBACK_TEXTS.keys())  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_play_calls_capture_frame_correct_count() -> None:
    pcm = b"\x00" * 640 * 3  # 3 full 20ms frames
    src = _make_audio_source()
    player = FallbackPlayer(src)
    await player.pregenerate(_make_tts(pcm), _make_text_processor())
    await player.play("asr_timeout")
    assert src.capture_frame.call_count == 3


@pytest.mark.asyncio
async def test_play_ungenerated_kind_is_noop_and_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    src = _make_audio_source()
    player = FallbackPlayer(src)
    # skip pregenerate → _audios is empty
    with caplog.at_level(logging.ERROR, logger="worker.audio.fallback"):
        await player.play("llm_error")
    src.capture_frame.assert_not_called()
    assert any("llm_error" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_is_ready_true_when_all_five_succeed() -> None:
    player = FallbackPlayer(_make_audio_source())
    await player.pregenerate(_make_tts(), _make_text_processor())
    assert player.is_ready is True


@pytest.mark.asyncio
async def test_is_ready_false_when_any_kind_fails() -> None:
    fail_kinds = {"asr_timeout"}

    async def _failing_synth(text: str):  # type: ignore[no-untyped-def]
        if text == "fake-asr":
            raise RuntimeError("synth failed")
        yield b"\x00" * 640

    def _proc_side_effect(zh: str) -> MagicMock:  # type: ignore[return]
        result = MagicMock()
        # map asr_timeout text → "fake-asr" to trigger failure
        result.taibun = "fake-asr" if zh == FALLBACK_TEXTS["asr_timeout"] else "ok"
        return result

    src = _make_audio_source()
    player = FallbackPlayer(src)
    tts = MagicMock()
    tts.synthesize = _failing_synth
    proc = MagicMock()
    proc.process.side_effect = _proc_side_effect
    await player.pregenerate(tts, proc)
    assert player.is_ready is False
    # other kinds should still be pregenerated
    assert len(player._audios) == len(FALLBACK_TEXTS) - len(fail_kinds)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_one_kind_failure_does_not_affect_others() -> None:
    fail_text = FALLBACK_TEXTS["asr_timeout"]

    async def _synth(text: str):  # type: ignore[no-untyped-def]
        if text == "will-fail":
            raise RuntimeError("synth error")
        yield b"\x00" * 640

    def _proc(zh: str) -> MagicMock:  # type: ignore[return]
        result = MagicMock()
        result.taibun = "will-fail" if zh == fail_text else "ok"
        return result

    tts = MagicMock()
    tts.synthesize = _synth
    proc = MagicMock()
    proc.process.side_effect = _proc

    player = FallbackPlayer(_make_audio_source())
    await player.pregenerate(tts, proc)

    # 4 of 5 should be ready
    assert len(player._audios) == 4  # pyright: ignore[reportPrivateUsage]
    assert "asr_timeout" not in player._audios  # pyright: ignore[reportPrivateUsage]
    for kind in ("llm_error", "tts_fail", "tool_error", "general"):
        assert kind in player._audios  # pyright: ignore[reportPrivateUsage]
