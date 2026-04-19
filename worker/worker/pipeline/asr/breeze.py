# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
import io
import os
import wave
from collections.abc import AsyncIterator

import aiohttp

from .base import ASRPartial, BaseASR


class BreezeASR26(BaseASR):
    def __init__(self) -> None:
        self._api_url = os.getenv(
            "ASR_URL", "http://localhost:8000/v1/audio/transcriptions"
        )

    async def warmup(self) -> None:
        # No local warmup needed, it's an API call
        pass

    async def stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[ASRPartial]:
        buffer = bytearray()
        async for chunk in audio_chunks:
            buffer.extend(chunk)

        text = await self._transcribe_full(bytes(buffer))
        yield ASRPartial(text=text, is_final=True)

    async def _transcribe_full(self, audio_bytes: bytes) -> str:
        # Convert raw 16kHz PCM to WAV format in memory
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_bytes)
        
        wav_data = wav_io.getvalue()

        form_data = aiohttp.FormData()
        form_data.add_field(
            "file",
            wav_data,
            filename="audio.wav",
            content_type="audio/wav",
        )
        form_data.add_field("language", "auto")
        form_data.add_field("max_gap_sec", "0.6")
        form_data.add_field("return_timestamps", "true")

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(self._api_url, data=form_data) as response,
            ):
                if response.status == 200:
                    result = await response.json()
                    return result.get("text", "")
                else:
                    text = await response.text()
                    raise RuntimeError(f"ASR API error: {response.status} {text}")
        except Exception as e:
            raise RuntimeError(f"Failed to call ASR API: {e}") from e

    @property
    def name(self) -> str:
        return "breeze-asr-26 (API)"
