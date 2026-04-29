from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from livekit import rtc

from ..observability.metrics import LatencyTimer
from ..pipeline.splitter import SmartSplitter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from ..db.repositories import InteractionLogRepository
    from .components import AgentComponents

logger = logging.getLogger("worker.session.runner")


class PipelineRunner:
    def __init__(self, components: AgentComponents) -> None:
        self._tts = components.tts
        self._asr = components.asr
        self._llm = components.llm
        self._memory = components.memory
        self._text_processor = components.text_processor
        self._audio_source = components.audio_source
        self._log_repo: InteractionLogRepository | None = components.log_repo
        self._session_id = components.session_id
        self._pipeline_busy = False
        self._utterance_seq = 0
        self._turn_index = 0

    async def speak_taibun(
        self,
        taibun: str,
        trace_id: str,
        on_first_audio: Callable[[], None] | None = None,
    ) -> None:
        if not self._tts:
            logger.warning(
                "[%s][tts] skipped because PiperTTS is unavailable", trace_id
            )
            return
        try:
            chunk_count = 0
            pcm_bytes = 0
            tts_start = time.perf_counter()
            # 20ms frames: 320 samples × 2 bytes = 640 bytes at 16kHz 16-bit mono
            chunk_size = 640
            leftover = b""
            first_frame = True
            async for chunk in self._tts.synthesize(taibun):
                chunk_count += 1
                pcm_bytes += len(chunk)
                data = leftover + chunk
                n_full = len(data) // chunk_size
                for j in range(n_full):
                    if first_frame:
                        if on_first_audio is not None:
                            on_first_audio()
                        first_frame = False
                    sub = data[j * chunk_size : (j + 1) * chunk_size]
                    await self._audio_source.capture_frame(
                        rtc.AudioFrame(
                            data=sub,
                            sample_rate=16000,
                            num_channels=1,
                            samples_per_channel=chunk_size // 2,
                        )
                    )
                leftover = data[n_full * chunk_size :]
            if leftover:
                if first_frame and on_first_audio is not None:
                    on_first_audio()
                padded = leftover + b"\x00" * (chunk_size - len(leftover))
                await self._audio_source.capture_frame(
                    rtc.AudioFrame(
                        data=padded,
                        sample_rate=16000,
                        num_channels=1,
                        samples_per_channel=chunk_size // 2,
                    )
                )
            logger.info(
                "[%s][tts] done chunks=%s bytes=%s cost_ms=%.1f",
                trace_id,
                chunk_count,
                pcm_bytes,
                (time.perf_counter() - tts_start) * 1000,
            )
        except Exception as e:
            logger.error("[%s][tts] failed: %s", trace_id, e)
            raise

    async def speak_notice(self, text: str, trace_id: str) -> None:
        res = self._text_processor.process(text)
        if res.taibun.strip():
            logger.info("[%s][notice] %s (%s)", trace_id, res.hanlo, res.taibun)
            try:
                await self.speak_taibun(res.taibun, trace_id)
            except Exception as e:
                logger.error(
                    "[%s][notice] tts failed, user will hear silence: %s",
                    trace_id,
                    e,
                )

    async def process_utterance(
        self, audio_bytes: bytes, source_tag: str = "unknown"
    ) -> None:
        # Safe without a lock: asyncio is single-threaded and there is no `await`
        # between the check and the assignment, so no concurrent task can interleave.
        # Do NOT insert an `await` between these two lines.
        if self._pipeline_busy:
            logger.info(
                "[pipeline] skipping utterance, previous still running bytes=%s",
                len(audio_bytes),
            )
            return
        self._pipeline_busy = True
        self._utterance_seq += 1
        trace_id = f"utt-{self._utterance_seq:04d}"
        pipeline_start = time.perf_counter()
        logger.info(
            "[%s][pipeline] start bytes=%s source=%s",
            trace_id,
            len(audio_bytes),
            source_tag,
        )

        timer = LatencyTimer.start()
        user_text: str = ""
        full_response: str = ""
        last_hanlo: str = ""
        last_taibun: str = ""
        error_flag: str | None = None

        # self-disabling callback: fires exactly once for the whole utterance
        _first_audio_fired = False

        def _on_first_audio() -> None:
            nonlocal _first_audio_fired
            if not _first_audio_fired:
                _first_audio_fired = True
                timer.mark("first_audio")

        try:
            asr_result = await self._run_asr(audio_bytes, trace_id)
            if asr_result is None:
                # _run_asr already played a notice on API errors
                return
            user_text = asr_result
            timer.mark("asr_end")

            if not user_text.strip():
                logger.info("[%s][asr] returned empty text", trace_id)
                await self.speak_notice(
                    "歹勢，我這馬聽無清楚，你閣講一遍好無？", trace_id
                )
                return

            logger.info("[%s][asr] user_text=%s", trace_id, user_text)
            self._memory.add("user", user_text)

            def _on_first_token() -> None:
                timer.mark("llm_first_tok")

            try:
                full_response, last_hanlo, last_taibun = await self._run_llm_tts(
                    trace_id,
                    on_first_token=_on_first_token,
                    on_first_audio=_on_first_audio,
                )
            except Exception:
                self._memory.pop_last()
                raise
        except Exception as e:
            if isinstance(e, TimeoutError):
                logger.error("[%s][pipeline] llm/text/tts timeout: %s", trace_id, e)
            else:
                logger.exception("[%s][pipeline] llm/text/tts failed: %r", trace_id, e)
            error_flag = "unknown"
            await self.speak_notice("歹勢，這馬無法回應，請稍後閣試。", trace_id)
        finally:
            timer.finalize()
            logger.info(
                "[%s][pipeline] end total_ms=%.1f",
                trace_id,
                (time.perf_counter() - pipeline_start) * 1000,
            )
            self._turn_index += 1
            if self._log_repo is not None and self._session_id:
                try:
                    await self._log_repo.log_turn(
                        session_id=self._session_id,
                        turn_index=self._turn_index,
                        user_asr_text=user_text,
                        llm_raw_text=full_response,
                        hanlo_text=last_hanlo or None,
                        taibun_text=last_taibun,
                        latencies=timer.as_dict(),
                        was_barged_in=False,
                        error_flag=error_flag,
                    )
                except Exception as log_err:
                    logger.error(
                        "[%s][log] failed to write interaction log: %s",
                        trace_id,
                        log_err,
                    )
            self._pipeline_busy = False

    async def _run_asr(self, audio_bytes: bytes, trace_id: str) -> str | None:
        async def _audio_gen() -> AsyncIterator[bytes]:
            yield audio_bytes

        asr_start = time.perf_counter()
        user_text = ""
        partial_count = 0
        try:
            async for partial in self._asr.stream(_audio_gen()):
                partial_count += 1
                if partial.is_final:
                    user_text = partial.text
            logger.info(
                "[%s][asr] done partials=%s text_len=%s cost_ms=%.1f",
                trace_id,
                partial_count,
                len(user_text),
                (time.perf_counter() - asr_start) * 1000,
            )
            return user_text
        except Exception as e:
            logger.error(
                "[%s][asr] failed cost_ms=%.1f error=%s",
                trace_id,
                (time.perf_counter() - asr_start) * 1000,
                e,
            )
            await self.speak_notice(
                "歹勢，語音辨識服務目前無法連線，請稍後再試。", trace_id
            )
            return None

    async def _run_llm_tts(
        self,
        trace_id: str,
        on_first_token: Callable[[], None] | None = None,
        on_first_audio: Callable[[], None] | None = None,
    ) -> tuple[str, str, str]:
        splitter = SmartSplitter()
        llm_start = time.perf_counter()
        full_response = ""
        first_token_ms: float | None = None
        token_count = 0
        last_hanlo = ""
        last_taibun = ""

        async for token in await self._llm.stream(messages=self._memory.to_messages()):
            token_count += 1
            if first_token_ms is None:
                first_token_ms = (time.perf_counter() - llm_start) * 1000
                logger.info("[%s][llm] first_token_ms=%.1f", trace_id, first_token_ms)
                if on_first_token is not None:
                    on_first_token()
            full_response += token
            for sentence in splitter.feed(token):
                hanlo, taibun = await self._speak_sentence(
                    sentence, trace_id, on_first_audio
                )
                if hanlo or taibun:
                    last_hanlo, last_taibun = hanlo, taibun

        rest = splitter.flush()
        if rest:
            hanlo, taibun = await self._speak_sentence(rest, trace_id, on_first_audio)
            if hanlo or taibun:
                last_hanlo, last_taibun = hanlo, taibun

        self._memory.add("assistant", full_response)
        logger.info(
            "[%s][llm] done tokens=%s response_len=%s cost_ms=%.1f",
            trace_id,
            token_count,
            len(full_response),
            (time.perf_counter() - llm_start) * 1000,
        )
        return full_response, last_hanlo, last_taibun

    async def _speak_sentence(
        self,
        sentence: str,
        trace_id: str,
        on_first_audio: Callable[[], None] | None = None,
    ) -> tuple[str, str]:
        logger.info("[%s][text] sentence=%s", trace_id, sentence)
        res = self._text_processor.process(sentence)
        if res.taibun.strip():
            logger.info("[%s][text] speaking=%s (%s)", trace_id, res.hanlo, res.taibun)
            await self.speak_taibun(res.taibun, trace_id, on_first_audio)
        return res.hanlo, res.taibun
