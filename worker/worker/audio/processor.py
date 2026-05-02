from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import numpy as np
from livekit import rtc
from livekit.agents.vad import VADEventType

from .voice_controller import VoiceState

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from ..session.runner import PipelineRunner
    from .vad import SileroVAD
    from .voice_controller import VoiceController

logger = logging.getLogger("worker.audio.processor")

_SAMPLE_RATE = 16000
_VAD_BUF_MAX = _SAMPLE_RATE * 2 * 30  # 30s @ 16kHz int16
_FALLBACK_MIN_SPEECH_SEC = 0.25
_FALLBACK_MIN_SILENCE_SEC = 0.6
_FALLBACK_MAX_SPEECH_SEC = 8.0
_FALLBACK_WINDOW_SEC = 2.5
_FORCED_WINDOW_SEC = 2.5
_FORCED_WINDOW_RMS_THRESHOLD = 10.0
# Single-frame probability threshold for the fast barge-in path (INFERENCE_DONE).
# Higher than activation_threshold (0.6) to avoid triggering on brief noise.
_BARGE_IN_PROB_THRESHOLD = 0.7


class AudioProcessor:
    def __init__(
        self,
        vad: SileroVAD,
        runner: PipelineRunner,
        voice_controller: VoiceController,
    ) -> None:
        self._vad = vad
        self._runner = runner
        self._vc = voice_controller
        self._bg_tasks: set[asyncio.Task[None]] = set()
        voice_controller.on_change(self._on_vc_change)

    def _on_vc_change(self, old: VoiceState, new: VoiceState) -> None:
        """Single on_change handler: VAD threshold adjustment + barge-in cleanup."""
        # VAD threshold: slightly elevated during SPEAKING to suppress TTS echo.
        if new == VoiceState.SPEAKING:
            self._vad.update_thresholds(
                activation_threshold=0.6, min_speech_duration=0.15
            )
        elif old == VoiceState.SPEAKING:
            self._vad.update_thresholds(
                activation_threshold=0.5, min_speech_duration=0.05
            )
        # Cleanup: triggered by the FSM transition, not by the caller.
        if new == VoiceState.BARGED_IN:
            self._spawn(self._barge_in_cleanup())

    async def _barge_in_cleanup(self) -> None:
        """Clear audio/TTS queues and cancel the active pipeline turn."""
        self._runner.audio_source.clear_queue()
        if self._runner.tts is not None:
            self._runner.tts.clear_queue()
        self._runner.cancel_current_turn()

    # Keep as a named method so tests can still reference it directly.
    def _apply_vad_thresholds(self, old: VoiceState, new: VoiceState) -> None:
        if new == VoiceState.SPEAKING:
            self._vad.update_thresholds(
                activation_threshold=0.6, min_speech_duration=0.15
            )
        elif old == VoiceState.SPEAKING:
            self._vad.update_thresholds(
                activation_threshold=0.5, min_speech_duration=0.05
            )

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task: asyncio.Task[None] = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    async def process_track(self, track: rtc.Track) -> None:
        audio_stream = rtc.AudioStream(track, sample_rate=_SAMPLE_RATE, num_channels=1)
        vad_stream = self._vad.stream()

        frame_count = 0
        vad_inference_count = 0

        # Fallback RMS-based VAD state
        fallback_speaking = False
        fallback_start_ts = 0.0
        fallback_last_voice_ts = 0.0
        fallback_buffer = bytearray()
        fallback_rms_noise_ema = 0.0
        fallback_has_noise_ema = False
        fallback_window_buffer = bytearray()

        now = asyncio.get_running_loop().time
        fallback_window_started_at = now()
        forced_window_buffer = bytearray()
        forced_window_started_at = now()

        vad_speech_buffer: bytearray = bytearray()
        vad_speech_started = False

        async def _consume_vad() -> None:
            nonlocal vad_inference_count
            nonlocal fallback_speaking, fallback_buffer
            nonlocal vad_speech_started
            try:
                async for event in vad_stream:
                    if event.type == VADEventType.INFERENCE_DONE:
                        vad_inference_count += 1
                        # Fast barge-in: don't wait for START_OF_SPEECH accumulation.
                        # Single frame above threshold → transition immediately.
                        # Cleanup (queue clear + cancel) fires via _on_vc_change.
                        if (
                            self._vc.state
                            in (VoiceState.SPEAKING, VoiceState.THINKING)
                            and event.probability > _BARGE_IN_PROB_THRESHOLD
                        ):
                            logger.info(
                                "Fast barge-in state=%s prob=%.3f",
                                self._vc.state.value,
                                event.probability,
                            )
                            self._vc.transition(VoiceState.BARGED_IN)
                        if vad_inference_count % 200 == 0:
                            logger.info(
                                "VAD inference events: %s prob=%.3f speaking=%s",
                                vad_inference_count,
                                event.probability,
                                event.speaking,
                            )
                        continue
                    if event.type == VADEventType.START_OF_SPEECH:
                        vad_speech_started = True
                        vad_speech_buffer.clear()
                        fallback_speaking = False
                        fallback_buffer.clear()
                        vc_state = self._vc.state
                        if vc_state == VoiceState.SPEAKING:
                            # Fast path (INFERENCE_DONE) usually fires first.
                            # This is the fallback if fast path missed.
                            logger.info("Barge-in via START_OF_SPEECH (fallback)")
                            self._vc.transition(VoiceState.BARGED_IN)
                        elif vc_state == VoiceState.THINKING:
                            # Barge-in during LLM generation (before first TTS frame).
                            logger.info("Barge-in during THINKING via START_OF_SPEECH")
                            self._vc.transition(VoiceState.BARGED_IN)
                        elif vc_state == VoiceState.LISTENING:
                            logger.info("VAD START while LISTENING (consecutive)")
                        else:
                            logger.info("VAD start of speech")
                    elif event.type == VADEventType.END_OF_SPEECH:
                        frames = event.frames if event.frames else []
                        if frames:
                            utterance = b"".join(_frame_bytes(f.data) for f in frames)
                        elif vad_speech_started:
                            utterance = bytes(vad_speech_buffer)
                        else:
                            utterance = b""
                        vad_speech_started = False
                        logger.info(
                            "VAD end of speech, frames=%s bytes=%s",
                            len(frames),
                            len(utterance),
                        )
                        if utterance:
                            self._vc.transition(VoiceState.LISTENING)
                            self._spawn(
                                self._runner.process_utterance(
                                    utterance, "vad_end_of_speech"
                                )
                            )
                        vad_speech_buffer.clear()
            except asyncio.CancelledError:
                logger.debug("VAD consumer cancelled (expected on track end)")
            except Exception as e:
                logger.error("VAD consumer failed: %s", e)
                raise

        consume_vad_task = asyncio.create_task(_consume_vad())

        try:
            async for frame_event in audio_stream:
                frame_count += 1
                if frame_count == 1:
                    logger.info(
                        "First audio frame: sample_rate=%s channels=%s"
                        " samples_per_channel=%s",
                        frame_event.frame.sample_rate,
                        frame_event.frame.num_channels,
                        frame_event.frame.samples_per_channel,
                    )
                elif frame_count % 200 == 0:
                    logger.info("Audio frames received: %s", frame_count)

                frame_bytes = _frame_bytes(frame_event.frame.data)
                vad_stream.push_frame(frame_event.frame)
                vad_speech_buffer.extend(frame_bytes)
                if len(vad_speech_buffer) > _VAD_BUF_MAX:
                    del vad_speech_buffer[: len(vad_speech_buffer) - _VAD_BUF_MAX]

                # Fallback + forced-window paths are only active while Silero VAD has
                # not yet emitted any inference event. Once it fires, Silero handles
                # segmentation and these paths stay dormant for the rest of the track.
                if vad_inference_count > 0:
                    continue
                t = now()

                # --- Forced window: triggers even if VAD never fires ---
                forced_window_buffer.extend(frame_bytes)
                if t - forced_window_started_at >= _FORCED_WINDOW_SEC:
                    if forced_window_buffer:
                        forced_rms = _rms(bytes(forced_window_buffer))
                        logger.info(
                            "Forced window monitor: rms=%.1f threshold=%.1f bytes=%s",
                            forced_rms,
                            _FORCED_WINDOW_RMS_THRESHOLD,
                            len(forced_window_buffer),
                        )
                        if forced_rms >= _FORCED_WINDOW_RMS_THRESHOLD:
                            logger.info(
                                "Forced window trigger, bytes=%s",
                                len(forced_window_buffer),
                            )
                            self._spawn(
                                self._runner.process_utterance(
                                    bytes(forced_window_buffer), "forced_window"
                                )
                            )
                    forced_window_buffer.clear()
                    forced_window_started_at = t

                # --- Fallback RMS VAD ---
                fallback_window_buffer.extend(frame_bytes)
                frame_rms = _rms(frame_bytes)

                if not fallback_has_noise_ema:
                    fallback_rms_noise_ema = frame_rms
                    fallback_has_noise_ema = True
                elif not fallback_speaking:
                    fallback_rms_noise_ema = (
                        fallback_rms_noise_ema * 0.98 + frame_rms * 0.02
                    )

                fallback_rms_threshold = max(12.0, fallback_rms_noise_ema * 1.6)
                has_voice = frame_rms >= fallback_rms_threshold

                if frame_count % 200 == 0:
                    logger.info(
                        "Fallback RMS monitor: rms=%.1f noise=%.1f"
                        " threshold=%.1f speaking=%s",
                        frame_rms,
                        fallback_rms_noise_ema,
                        fallback_rms_threshold,
                        fallback_speaking,
                    )

                if t - fallback_window_started_at >= _FALLBACK_WINDOW_SEC:
                    if fallback_window_buffer:
                        window_rms = _rms(bytes(fallback_window_buffer))
                        if window_rms >= fallback_rms_threshold:
                            logger.info(
                                "Fallback window trigger, bytes=%s"
                                " window_rms=%.1f threshold=%.1f",
                                len(fallback_window_buffer),
                                window_rms,
                                fallback_rms_threshold,
                            )
                            self._spawn(
                                self._runner.process_utterance(
                                    bytes(fallback_window_buffer), "fallback_window"
                                )
                            )
                    fallback_window_buffer.clear()
                    fallback_window_started_at = t

                if has_voice:
                    if not fallback_speaking:
                        fallback_speaking = True
                        fallback_start_ts = t
                        fallback_buffer.clear()
                        logger.info("Fallback VAD start, rms=%.1f", frame_rms)
                    fallback_last_voice_ts = t
                    fallback_buffer.extend(frame_bytes)
                elif fallback_speaking:
                    fallback_buffer.extend(frame_bytes)
                    if t - fallback_last_voice_ts >= _FALLBACK_MIN_SILENCE_SEC:
                        speech_sec = t - fallback_start_ts
                        if speech_sec >= _FALLBACK_MIN_SPEECH_SEC:
                            logger.info(
                                "Fallback VAD end, bytes=%s speech_sec=%.2f",
                                len(fallback_buffer),
                                speech_sec,
                            )
                            self._spawn(
                                self._runner.process_utterance(
                                    bytes(fallback_buffer), "fallback_end_of_speech"
                                )
                            )
                        fallback_speaking = False
                        fallback_buffer.clear()

                if fallback_speaking and (
                    t - fallback_start_ts >= _FALLBACK_MAX_SPEECH_SEC
                ):
                    logger.info(
                        "Fallback max speech reached, bytes=%s speech_sec=%.2f",
                        len(fallback_buffer),
                        t - fallback_start_ts,
                    )
                    self._spawn(
                        self._runner.process_utterance(
                            bytes(fallback_buffer), "fallback_max_speech"
                        )
                    )
                    fallback_speaking = False
                    fallback_buffer.clear()
        except Exception as e:
            logger.error("Audio stream processing failed: %s", e)
            raise
        finally:
            consume_vad_task.cancel()
            try:
                await consume_vad_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("VAD consumer task exited with error: %s", e)


def _frame_bytes(data: Any) -> bytes:
    return data.tobytes() if hasattr(data, "tobytes") else bytes(data)


def _rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(np.square(arr))))
