import asyncio
import io
import os
import unicodedata
import wave
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import numpy as np
from piper.config import SynthesisConfig
from piper.voice import PiperVoice


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class PiperTTS:
    def __init__(self, model_path: str, speaker_id: int | None = None) -> None:
        self.model_path = model_path
        self.speaker_id = speaker_id
        self._clear_event = asyncio.Event()
        self.executor = ThreadPoolExecutor(max_workers=1)

        self.api_url = os.getenv("PIPER_TTS_API_URL")
        self.api_model = os.getenv("PIPER_TTS_MODEL", "taigi_epoch1339")
        self.api_voice = os.getenv("PIPER_TTS_VOICE", self.api_model)
        self.api_speed = _read_float_env("PIPER_TTS_SPEED", 1.1)
        self.api_noise_scale = _read_float_env("PIPER_TTS_NOISE_SCALE", 0.8)
        self.api_noise_scale_w = _read_float_env("PIPER_TTS_NOISE_SCALE_W", 0.8)

        self.voice: PiperVoice | None = None
        if not self.api_url:
            self.voice = PiperVoice.load(model_path)

    async def synthesize(self, taibun_text: str) -> AsyncIterator[bytes]:
        self._clear_event.clear()
        if self.api_url:
            pcm = await self._synthesize_http(taibun_text)
            if not self._clear_event.is_set() and pcm:
                yield pcm
            return

        if self.voice is None:
            raise RuntimeError("Piper voice is not initialized")

        # To avoid blocking the event loop and handle barge-in gracefully,
        # run the synthesis in a thread and yield chunks.
        queue: asyncio.Queue[bytes | Exception | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _synthesize_task() -> None:
            try:
                syn_config = SynthesisConfig(speaker_id=self.speaker_id)
                for chunk in self.voice.synthesize(
                    taibun_text, syn_config=syn_config
                ):  # type: ignore
                    if self._clear_event.is_set():
                        break

                    # chunk is typed as unknown
                    audio_bytes: bytes | None = chunk.audio_int16_bytes  # type: ignore
                    if audio_bytes:
                        loop.call_soon_threadsafe(queue.put_nowait, audio_bytes)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        self.executor.submit(_synthesize_task)

        while True:
            if self._clear_event.is_set():
                break

            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item

            yield item

    async def _synthesize_http(self, taibun_text: str) -> bytes:
        if not self.api_url:
            raise RuntimeError("PIPER_TTS_API_URL is not configured")

        normalized_text = self._normalize_tts_input(taibun_text)
        if not normalized_text:
            return b""

        payload = {
            "model": self.api_model,
            "voice": self.api_voice,
            "input": normalized_text,
            "response_format": "wav",
            "speed": self.api_speed,
            "noise_scale": self.api_noise_scale,
            "noise_scale_w": self.api_noise_scale_w,
        }

        last_error: Exception | None = None
        for _attempt in range(1, 4):
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.post(self.api_url, json=payload) as response,
                ):
                    if response.status != 200:
                        text = await response.text()
                        err = RuntimeError(f"TTS API error: {response.status} {text}")
                        if 400 <= response.status < 500:
                            # Permanent client error — bad input, wrong model name, etc.
                            # Retrying won't help; surface immediately.
                            raise err
                        # 5xx transient server error — fall through to retry
                        last_error = err
                    else:
                        wav_bytes = await response.read()
                        return self._wav_to_pcm(wav_bytes)
            except RuntimeError:
                raise  # Re-raise permanent errors (4xx) without sleeping
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
            await asyncio.sleep(0.2 * _attempt)

        raise RuntimeError(f"Failed to call TTS API after retries: {last_error}") from last_error

    @staticmethod
    def _wav_to_pcm(wav_bytes: bytes) -> bytes:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_reader:
            channels = wav_reader.getnchannels()
            sample_width = wav_reader.getsampwidth()
            frame_rate = wav_reader.getframerate()
            raw = wav_reader.readframes(wav_reader.getnframes())

        if sample_width == 1:
            arr: np.ndarray = (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) * 256
        elif sample_width == 2:
            arr = np.frombuffer(raw, dtype=np.int16).copy()
        elif sample_width == 4:
            arr = (np.frombuffer(raw, dtype=np.int32) >> 16).astype(np.int16)
        else:
            raise RuntimeError(f"TTS returned unsupported sample width: {sample_width}")

        if channels > 1:
            arr = arr.reshape(-1, channels).mean(axis=1).astype(np.int16)

        if frame_rate != 16000:
            num_out = int(round(len(arr) * 16000 / frame_rate))
            arr = np.interp(
                np.linspace(0, len(arr) - 1, num_out),
                np.arange(len(arr)),
                arr.astype(np.float32),
            ).astype(np.int16)

        return arr.tobytes()

    @staticmethod
    def _normalize_tts_input(text: str) -> str:
        # Strip emoji and other symbol-only characters that frequently break
        # third-party TTS HTTP backends with malformed chunked responses.
        cleaned_chars: list[str] = []
        for ch in text:
            cat = unicodedata.category(ch)
            if cat.startswith("C"):  # control/surrogate/private-use/unassigned
                continue
            if cat == "So":  # symbol other (e.g. emoji)
                continue
            cleaned_chars.append(ch)
        return "".join(cleaned_chars).strip()

    def clear_queue(self) -> None:
        self._clear_event.set()

    def close(self) -> None:
        self.executor.shutdown(wait=False)
