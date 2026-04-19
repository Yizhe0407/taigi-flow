import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

from piper.config import SynthesisConfig
from piper.voice import PiperVoice


class PiperTTS:
    def __init__(self, model_path: str, speaker_id: int | None = None) -> None:
        self.model_path = model_path
        self.speaker_id = speaker_id
        # load piper voice
        self.voice = PiperVoice.load(model_path)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._clear_event = asyncio.Event()

    async def synthesize(self, taibun_text: str) -> AsyncIterator[bytes]:
        self._clear_event.clear()

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

            # Block until a chunk is available
            item = await queue.get()

            if item is None:
                break
            if isinstance(item, Exception):
                raise item

            yield item

    def clear_queue(self) -> None:
        self._clear_event.set()
