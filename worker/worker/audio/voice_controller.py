from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from livekit import rtc

    from ..pipeline.tts import PiperTTS
    from ..session.runner import PipelineRunner

logger = logging.getLogger("worker.audio.voice_controller")


class VoiceState(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    BARGED_IN = "barged_in"


def _cb_list() -> list[Callable[[VoiceState, VoiceState], None]]:
    return []


_TRANSITIONS: dict[VoiceState, set[VoiceState]] = {
    VoiceState.IDLE: {VoiceState.LISTENING},
    VoiceState.LISTENING: {VoiceState.THINKING, VoiceState.IDLE},
    VoiceState.THINKING: {VoiceState.SPEAKING, VoiceState.IDLE, VoiceState.BARGED_IN},
    VoiceState.SPEAKING: {VoiceState.IDLE, VoiceState.BARGED_IN},
    VoiceState.BARGED_IN: {VoiceState.LISTENING, VoiceState.IDLE},
}


@dataclass
class VoiceController:
    """Pure state machine + self-speech suppression timestamp. No I/O; transition
    side-effects are injected via on_change callbacks."""

    _state: VoiceState = field(default=VoiceState.IDLE)
    _last_tts_output_ts: float = field(default=0.0)
    _on_change: list[Callable[[VoiceState, VoiceState], None]] = field(
        default_factory=_cb_list
    )

    @property
    def state(self) -> VoiceState:
        return self._state

    def transition(self, new_state: VoiceState) -> None:
        """Change state. Illegal transitions log a warning but still apply (fail-soft).
        """
        old = self._state
        if old == new_state:
            return
        if new_state not in _TRANSITIONS.get(old, set()):
            logger.warning(
                "[vc] illegal transition %s → %s (forced)", old.value, new_state.value
            )
        else:
            logger.info("[vc] %s → %s", old.value, new_state.value)
        self._state = new_state
        for cb in self._on_change:
            try:
                cb(old, new_state)
            except Exception:
                logger.exception("[vc] on_change callback raised")

    def is_speaking(self) -> bool:
        return self._state == VoiceState.SPEAKING

    def mark_tts_output(self) -> None:
        """Record the moment of the most recent TTS frame push.
        Used for self-speech suppression."""
        self._last_tts_output_ts = time.perf_counter()

    def time_since_last_tts_ms(self) -> float:
        if self._last_tts_output_ts == 0.0:
            return float("inf")
        return (time.perf_counter() - self._last_tts_output_ts) * 1000

    def on_change(self, cb: Callable[[VoiceState, VoiceState], None]) -> None:
        """Register a state-change callback. Called in registration order."""
        self._on_change.append(cb)

    async def on_barge_in(
        self,
        *,
        runner: PipelineRunner,
        tts: PiperTTS | None,
        audio_source: rtc.AudioSource,
    ) -> None:
        """Six-step barge-in cleanup sequence (order is mandatory):
        1. Discard buffered audio frames immediately.
        2. Signal TTS synth thread to stop at next chunk boundary.
        3. Cancel the current pipeline turn task (cascades to all TTS sub-tasks).
        4-5. (handled by process_utterance finally / task GC)
        6. Transition to BARGED_IN; caller's finally will transition to LISTENING.
        """
        audio_source.clear_queue()
        if tts is not None:
            tts.clear_queue()
        runner.cancel_current_turn()
        self.transition(VoiceState.BARGED_IN)
