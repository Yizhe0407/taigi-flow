from livekit.agents.vad import VADStream
from livekit.plugins.silero import VAD


class SileroVAD:
    """Wrapper around LiveKit's Silero VAD plugin."""

    def __init__(self) -> None:
        self._vad = VAD.load()

    def stream(self) -> VADStream:
        return self._vad.stream()

    def update_thresholds(
        self,
        activation_threshold: float | None = None,
        deactivation_threshold: float | None = None,
        min_speech_duration: float | None = None,
        min_silence_duration: float | None = None,
    ) -> None:
        """Update VAD thresholds dynamically."""
        kwargs: dict[str, float] = {}
        if activation_threshold is not None:
            kwargs["activation_threshold"] = activation_threshold
        if deactivation_threshold is not None:
            kwargs["deactivation_threshold"] = deactivation_threshold
        if min_speech_duration is not None:
            kwargs["min_speech_duration"] = min_speech_duration
        if min_silence_duration is not None:
            kwargs["min_silence_duration"] = min_silence_duration

        if kwargs:
            self._vad.update_options(**kwargs)
