# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
import os
from collections.abc import AsyncIterator

import aiohttp

from .base import ASRPartial, BaseASR, pcm_to_wav


class BreezeASR26(BaseASR):
    def __init__(self) -> None:
        self._api_url = os.getenv(
            "BREEZE_ASR_URL",
            os.getenv("ASR_URL", "http://localhost:8000/v1/audio/transcriptions"),
        )
        self._model = os.getenv("BREEZE_ASR_MODEL", "breeze-asr-26")

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
        wav_data = pcm_to_wav(audio_bytes)

        form_data = aiohttp.FormData()
        form_data.add_field(
            "file",
            wav_data,
            filename="audio.wav",
            content_type="audio/wav",
        )
        form_data.add_field("language", "zh")
        form_data.add_field("model", self._model)
        form_data.add_field("max_gap_sec", "0.6")
        form_data.add_field("return_timestamps", "true")

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
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
        return f"{self._model} (API)"
