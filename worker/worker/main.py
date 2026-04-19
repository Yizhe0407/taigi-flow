# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false, reportUnusedFunction=false
import asyncio
import logging

import numpy as np
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.vad import VADEventType

from .controller.vad import SileroVAD
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
        # P2-07 Dummy Loop: we assume a model exists at "models/taigi.onnx"
        # Since it might not exist during CI, we wrap it in try-except
        tts = PiperTTS(model_path="models/taigi.onnx")
    except Exception as e:
        logger.warning(f"PiperTTS init failed (maybe no model?): {e}")
        tts = None

    async def _speak_dummy(text: str) -> None:
        if not tts:
            logger.info(f"Speaking dummy text (no TTS loaded): {text}")
            return

        logger.info(f"Speaking: {text}")
        try:
            async for chunk in tts.synthesize(text):
                audio_array = np.frombuffer(chunk, dtype=np.int16)
                frame = rtc.AudioFrame(
                    data=chunk,
                    sample_rate=16000,
                    num_channels=1,
                    samples_per_channel=len(audio_array),
                )
                # capture_frame is synchronous
                await asyncio.to_thread(source.capture_frame, frame)
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")

    # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator, reportUnusedFunction]
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

                async def _consume_vad() -> None:
                    async for event in vad_stream:
                        if event.type == VADEventType.END_OF_SPEECH:
                            logger.info("VAD detected end of speech. Triggering TTS.")
                            asyncio.create_task(_speak_dummy("你好，我是 Agent"))

                asyncio.create_task(_consume_vad())

                async for frame_event in audio_stream:
                    vad_stream.push_frame(frame_event.frame)

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
