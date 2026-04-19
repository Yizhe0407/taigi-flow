# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false, reportUnusedFunction=false
import asyncio
import logging
import os

import numpy as np
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.vad import VADEventType

from .controller.vad import SileroVAD
from .pipeline.asr.base import BaseASR  # noqa: TC001
from .pipeline.asr.breeze import BreezeASR26
from .pipeline.asr.qwen3 import Qwen3ASR
from .pipeline.llm import LLMClient
from .pipeline.memory import SlidingWindowMemory
from .pipeline.splitter import SmartSplitter
from .pipeline.text_processor import TextProcessor
from .pipeline.tts import PiperTTS

logger = logging.getLogger("worker")


async def entrypoint(ctx: JobContext) -> None:
    logger.info("Agent starting...")

    # 訂閱使用者音訊
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Connected to room: {ctx.room.name}")

    # 發佈 Agent 音訊 (建立音訊來源與軌道)
    source = rtc.AudioSource(16000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("agent-mic", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)

    publication = await ctx.room.local_participant.publish_track(track, options)
    logger.info(f"Published agent audio track: {publication.sid}")

    vad = SileroVAD()

    try:
        tts = PiperTTS(model_path="models/taigi.onnx")
    except Exception as e:
        logger.warning(f"PiperTTS init failed: {e}")
        tts = None

    asr_name = os.getenv("ASR_BACKEND", "qwen3")
    asr: BaseASR = Qwen3ASR() if asr_name == "qwen3" else BreezeASR26()
    
    logger.info(f"Warming up ASR: {asr.name}")
    try:
        await asr.warmup()
    except Exception as e:
        logger.error(f"ASR warmup failed: {e}")

    llm = LLMClient(
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model="gpt-4o-mini",
    )
    memory = SlidingWindowMemory(
        system_prompt="你是一個會講台語的 AI 助理。請用繁體中文（漢羅混寫）回答。"
    )
    text_processor = TextProcessor()
    await text_processor.load_dictionary()

    async def _speak_taibun(taibun: str) -> None:
        if not tts:
            return
        try:
            async for chunk in tts.synthesize(taibun):
                audio_array = np.frombuffer(chunk, dtype=np.int16)
                frame = rtc.AudioFrame(
                    data=chunk,
                    sample_rate=16000,
                    num_channels=1,
                    samples_per_channel=len(audio_array),
                )
                await asyncio.to_thread(source.capture_frame, frame)
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")

    async def _process_utterance(audio_bytes: bytes) -> None:
        logger.info("Processing utterance...")

        # 1. ASR
        async def _audio_gen():
            yield audio_bytes
            
        user_text = ""
        try:
            async for partial in asr.stream(_audio_gen()):
                if partial.is_final:
                    user_text = partial.text
        except Exception as e:
            logger.error(f"ASR failed: {e}")
            return

        if not user_text.strip():
            logger.info("ASR returned empty string.")
            return

        logger.info(f"User said: {user_text}")
        memory.add("user", user_text)

        # 2. LLM
        splitter = SmartSplitter()
        try:
            full_response = ""
            async for token in await llm.stream(messages=memory.to_messages()):
                full_response += token
                sentences = splitter.feed(token)
                for sentence in sentences:
                    # 3. Text Pipeline & 4. TTS
                    res = text_processor.process(sentence)
                    if res.taibun.strip():
                        logger.info(f"Speaking: {res.hanlo} ({res.taibun})")
                        await _speak_taibun(res.taibun)

            rest = splitter.flush()
            if rest:
                res = text_processor.process(rest)
                if res.taibun.strip():
                    logger.info(f"Speaking: {res.hanlo} ({res.taibun})")
                    await _speak_taibun(res.taibun)

            memory.add("assistant", full_response)
        except Exception as e:
            logger.error(f"LLM/Pipeline failed: {e}")

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        pub: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info("Subscribed to audio track")
            
            async def _process_audio() -> None:
                audio_stream = rtc.AudioStream(track)
                vad_stream = vad.stream()

                is_speaking = False
                speech_buffer = bytearray()

                async def _consume_vad() -> None:
                    nonlocal is_speaking, speech_buffer
                    async for event in vad_stream:
                        if event.type == VADEventType.START_OF_SPEECH:
                            is_speaking = True
                            speech_buffer.clear()
                        elif event.type == VADEventType.END_OF_SPEECH:
                            if is_speaking:
                                is_speaking = False
                                asyncio.create_task(_process_utterance(bytes(speech_buffer)))
                                speech_buffer.clear()

                asyncio.create_task(_consume_vad())

                async for frame_event in audio_stream:
                    vad_stream.push_frame(frame_event.frame)
                    if is_speaking:
                        speech_buffer.extend(frame_event.frame.data)

            asyncio.create_task(_process_audio())

    # Keep the job running
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Agent stopped.")


def main() -> None:
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="taigi-agent",
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
