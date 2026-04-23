# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false, reportUnusedFunction=false
import asyncio
import logging
import os

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, JobRequest, WorkerOptions, cli

from .audio.processor import AudioProcessor
from .audio.vad import SileroVAD
from .session.components import build_components
from .session.runner import PipelineRunner

logger = logging.getLogger("worker")


async def request_fnc(req: JobRequest) -> None:
    logger.info("Accepting job for room %s", req.room.name)
    await req.accept()


async def entrypoint(ctx: JobContext) -> None:
    logger.info("Agent starting...")

    components = await build_components()

    track = rtc.LocalAudioTrack.create_audio_track("agent-mic", components.audio_source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)

    vad = SileroVAD()
    runner = PipelineRunner(components)
    processor = AudioProcessor(vad=vad, runner=runner)
    active_audio_tracks: set[str] = set()
    _track_tasks: set[asyncio.Task[None]] = set()

    def _start_track(
        track: rtc.Track,
        pub: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if pub.sid in active_audio_tracks:
            return
        active_audio_tracks.add(pub.sid)
        logger.info(
            "Subscribed to audio track: participant=%s source=%s sid=%s",
            participant.identity,
            pub.source,
            pub.sid,
        )
        track_sid = pub.sid

        async def _run() -> None:
            try:
                await processor.process_track(track)
            finally:
                active_audio_tracks.discard(track_sid)

        task = asyncio.create_task(_run())
        _track_tasks.add(task)
        task.add_done_callback(_track_tasks.discard)

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        pub: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        _start_track(track, pub, participant)

    @ctx.room.on("track_unsubscribed")
    def on_track_unsubscribed(
        track: rtc.Track,
        pub: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if pub.sid in active_audio_tracks:
            active_audio_tracks.discard(pub.sid)
            logger.info(
                "Unsubscribed audio track: participant=%s sid=%s",
                participant.identity,
                pub.sid,
            )

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Connected to room: %s", ctx.room.name)

    publication = await ctx.room.local_participant.publish_track(track, options)
    logger.info("Published agent audio track: %s", publication.sid)

    # Handle tracks already subscribed before our handlers were registered
    for participant in ctx.room.remote_participants.values():
        for pub in participant.track_publications.values():
            if pub.track and pub.subscribed:
                assert isinstance(pub.track, rtc.Track)
                _start_track(pub.track, pub, participant)

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Agent stopped.")


def main() -> None:
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            request_fnc=request_fnc,
            agent_name="taigi-agent",
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
