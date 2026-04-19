# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
import io
import os
import wave
from collections.abc import AsyncIterator

import aiohttp

from .base import ASRPartial, BaseASR


class Qwen3ASR(BaseASR):
    def __init__(self) -> None:
        self._api_url = os.getenv(
            "ASR_URL", "http://localhost:8000/v1/audio/transcriptions"
        )

    async def warmup(self) -> None:
        pass

    async def stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[ASRPartial]:
        # Since the provided API endpoint (v1/audio/transcriptions) expects a file,
        # it is a batch endpoint. We accumulate the chunks and send them.
        buffer = bytearray()
        async for chunk in audio_chunks:
            buffer.extend(chunk)

        # Convert raw 16kHz PCM to WAV format in memory
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)
            wav_file.writeframes(bytes(buffer))
        
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
                    text = result.get("text", "")
                    yield ASRPartial(text=text, is_final=True)
                else:
                    err_text = await response.text()
                    raise RuntimeError(
                        f"ASR API error: {response.status} {err_text}"
                    )
        except Exception as e:
            raise RuntimeError(f"Failed to call ASR API: {e}") from e

    @property
    def name(self) -> str:
        return "qwen3-asr-0.6b (API)"
