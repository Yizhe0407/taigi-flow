from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

import numpy as np
from livekit import rtc
from livekit.agents.vad import VADEventType

from ..session.runner import PipelineRunner
from .vad import SileroVAD

logger = logging.getLogger("worker.audio.processor")

_SAMPLE_RATE = 16000
_VAD_BUF_MAX = _SAMPLE_RATE * 2 * 30  # 30s @ 16kHz int16
_FALLBACK_MIN_SPEECH_SEC = 0.25
_FALLBACK_MIN_SILENCE_SEC = 0.6
_FALLBACK_MAX_SPEECH_SEC = 8.0
_FALLBACK_WINDOW_SEC = 2.5
_FORCED_WINDOW_SEC = 2.5
_FORCED_WINDOW_RMS_THRESHOLD = 10.0


class AudioProcessor:
    def __init__(self, vad: SileroVAD, runner: PipelineRunner) -> None:
        self._vad = vad
        self._runner = runner
        self._bg_tasks: set[asyncio.Task[None]] = set()

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
                        logger.info("VAD start of speech")
                        vad_speech_buffer.clear()
                        fallback_speaking = False
                        fallback_buffer.clear()
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
                            self._spawn(
                                self._runner.process_utterance(utterance, "vad_end_of_speech")
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
                        "First audio frame: sample_rate=%s channels=%s samples_per_channel=%s",
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
                            logger.info("Forced window trigger, bytes=%s", len(forced_window_buffer))
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
                    fallback_rms_noise_ema = fallback_rms_noise_ema * 0.98 + frame_rms * 0.02

                fallback_rms_threshold = max(12.0, fallback_rms_noise_ema * 1.6)
                has_voice = frame_rms >= fallback_rms_threshold

                if frame_count % 200 == 0:
                    logger.info(
                        "Fallback RMS monitor: rms=%.1f noise=%.1f threshold=%.1f speaking=%s",
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
                                "Fallback window trigger, bytes=%s window_rms=%.1f threshold=%.1f",
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

                if fallback_speaking and t - fallback_start_ts >= _FALLBACK_MAX_SPEECH_SEC:
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
