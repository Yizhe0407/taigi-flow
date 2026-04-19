import asyncio
import logging

from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli

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

    # Keep the job running
    # 這裡的邏輯在 P2-07 Dummy Loop 中會被替換
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
