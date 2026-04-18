"""CLI for text-only conversation testing."""

from __future__ import annotations

import argparse
import asyncio
import os
import time

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from worker.db.repositories import AgentProfileRepository, InteractionLogRepository
from worker.db.session import AsyncSessionFactory
from worker.pipeline.llm import LLMClient
from worker.pipeline.memory import SlidingWindowMemory
from worker.pipeline.splitter import SmartSplitter
from worker.pipeline.text_processor import TextProcessor


def _make_llm() -> LLMClient:
    return LLMClient(
        base_url=os.environ.get(
            "LLM_BASE_URL", "http://100.107.45.116:11434/v1"
        ),
        api_key=os.environ.get("LLM_API_KEY", "ollama"),
        model=os.environ.get("LLM_MODEL", "frob/qwen3.5-instruct:4b"),
    )


async def run(profile_name: str) -> None:
    log_repo = InteractionLogRepository(AsyncSessionFactory)

    async with AsyncSessionFactory() as db:
        profile_repo = AgentProfileRepository(db)
        profile = await profile_repo.get_active_by_name(profile_name)
        if profile is None:
            print(f"Profile '{profile_name}' not found or inactive.")
            return

    memory = SlidingWindowMemory(max_turns=12, system_prompt=profile.systemPrompt)
    text_proc = TextProcessor(profile_id=profile.id, db_session=None)
    llm = _make_llm()

    session_id = await log_repo.create_session(profile.id, "cli-session")
    print(f"Session: {session_id}\nProfile: {profile.name}\n")
    print("Type your message. Ctrl+C to exit.\n")

    turn_index = 0
    try:
        while True:
            try:
                user_input = input("You > ").strip()
            except EOFError:
                break
            if not user_input:
                continue

            async with AsyncSessionFactory() as db:
                await text_proc.reload_if_updated(db)

            memory.add("user", user_input)
            messages = memory.to_messages()

            splitter = SmartSplitter()
            llm_full: list[str] = []
            all_hanlo: list[str] = []
            all_taibun: list[str] = []

            t_start = time.perf_counter()
            t_first_tok: float | None = None

            print("Assistant >")
            print("  [LLM]    ", end="", flush=True)
            try:
                stream = await llm.stream(messages)
                async for token in stream:
                    if t_first_tok is None:
                        t_first_tok = time.perf_counter()
                    llm_full.append(token)
                    print(token, end="", flush=True)
                    for chunk in splitter.feed(token):
                        result = text_proc.process(chunk)
                        all_hanlo.append(result.hanlo)
                        all_taibun.append(result.taibun)
                        print(f"\n  [CHUNK]  「{chunk}」")
                        print(f"  [HANLO]  {result.hanlo}")
                        print(f"  [TAIBUN] {result.taibun}")
                        print("  [LLM]    ", end="", flush=True)
                print()

                remainder = splitter.flush()
                if remainder.strip():
                    result = text_proc.process(remainder)
                    all_hanlo.append(result.hanlo)
                    all_taibun.append(result.taibun)
                    print(f"  [CHUNK]  「{remainder}」")
                    print(f"  [HANLO]  {result.hanlo}")
                    print(f"  [TAIBUN] {result.taibun}")

            except asyncio.TimeoutError:
                print("\n[ERROR] LLM timeout")

            t_end = time.perf_counter()
            llm_raw = "".join(llm_full)
            memory.add("assistant", llm_raw)

            first_tok_ms = int((t_first_tok - t_start) * 1000) if t_first_tok else None
            total_ms = int((t_end - t_start) * 1000)
            print(
                f"[Latency] ASR end N/A | LLM first tok {first_tok_ms}ms | Total {total_ms}ms\n"
            )

            await log_repo.log_turn(
                session_id=session_id,
                turn_index=turn_index,
                user_asr_text=user_input,
                llm_raw_text=llm_raw,
                hanlo_text=" ".join(all_hanlo) or None,
                taibun_text=" ".join(all_taibun),
                latencies={
                    **({"llm_first_tok": first_tok_ms} if first_tok_ms else {}),
                    "total": total_ms,
                },
            )
            turn_index += 1

    except KeyboardInterrupt:
        print("\n\nExiting...")
    finally:
        await log_repo.end_session(session_id)
        print(f"Session ended. {turn_index} turns logged.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Taigi-Flow text-only CLI")
    parser.add_argument("--profile", required=True, help="Agent profile name")
    args = parser.parse_args()
    asyncio.run(run(args.profile))


if __name__ == "__main__":
    main()
