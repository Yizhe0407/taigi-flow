# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
import os
from collections.abc import AsyncIterator

import aiohttp

from .base import ASRPartial, BaseASR, pcm_to_wav


class Qwen3ASR(BaseASR):
    def __init__(self) -> None:
        self._api_url = os.getenv(
            "QWEN3_ASR_URL",
            os.getenv("ASR_URL", "http://localhost:8001/v1/audio/transcriptions"),
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

        wav_data = pcm_to_wav(bytes(buffer))

        form_data = aiohttp.FormData()
        form_data.add_field(
            "file",
            wav_data,
            filename="audio.wav",
            content_type="audio/wav",
        )
        form_data.add_field("language", "chinese")
        form_data.add_field("prompt", "")
        form_data.add_field("max_new_tokens", "512")
        form_data.add_field("max_inference_batch_size", "32")
        form_data.add_field("return_timestamps", "false")
        form_data.add_field("max_gap_sec", "0.6")
        form_data.add_field("max_chars", "40")
        form_data.add_field("split_mode", "length")

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
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
        return "qwen3-asr (API)"
