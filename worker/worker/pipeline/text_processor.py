from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import taibun.taibun as _taibun_module  # type: ignore[import-untyped]
from sqlalchemy import func, select
from taibun import Converter  # type: ignore[import-untyped]
from taigi_converter import TaigiConverter  # type: ignore[import-untyped]

from worker.db.models import PronunciationEntry

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

# Patch chars missing from taibun.
# word_dict (words.msgpack) = char → romanization str; checked by WordDict.__contains__
# prons_dict (prons.msgpack) = char → list[str]; used for variant lookups
# Both must be patched before any Converter is created.
_TAIBUN_PATCHES: dict[str, str] = {
    "妳": "lí",
    "您": "lín",
    "她": "i",
    "它": "i",
    "牠": "i",
    "嘞": "leh",
    "啪": "phah",
    "嗎": "ma",
    "嘸": "bô",
    "呣": "m̄",
    "咧": "leh",
    "囉": "lô",
    "啦": "la",
    "喔": "oh",
    "欸": "eh",
    "唷": "ioh",
    "嬤": "má",
    "們": "mûn",
    "们": "mûn",
    "佢": "i",
    "哦": "oh",
    "呀": "ah",
    "嘅": "ê",
    "儂": "lâng",
    "怹": "in",
    "儕": "tsê",
}
for _ch, _rom in _TAIBUN_PATCHES.items():
    word_dict: dict[str, str] = _taibun_module.word_dict  # type: ignore[assignment]
    prons_dict: dict[str, list[str]] = _taibun_module.prons_dict  # type: ignore[assignment]
    word_dict.setdefault(_ch, _rom)  # pyright: ignore[reportUnknownMemberType]
    prons_dict.setdefault(_ch, [_rom])  # pyright: ignore[reportUnknownMemberType]

_PROTECTED = re.compile(r"⟨([^⟩]*)⟩")


@dataclass
class ProcessResult:
    hanlo: str
    taibun: str


class TextProcessor:
    def __init__(
        self,
        profile_id: str | None = None,
        db_session: AsyncSession | None = None,
    ) -> None:
        self._profile_id = profile_id
        self._db_session = db_session
        self._dictionary: list[PronunciationEntry] = []
        self._dict_last_updated: datetime | None = None
        self._hanlo: Any = TaigiConverter()
        self._taibun: Any = Converter(system="Tailo", format="number")

    def _dict_query(self) -> Select[tuple[PronunciationEntry]]:
        return select(PronunciationEntry).where(
            (PronunciationEntry.profileId == self._profile_id)
            | (PronunciationEntry.profileId.is_(None))
        )

    async def load_dictionary(self) -> None:
        if self._db_session is None:
            return
        result = await self._db_session.execute(self._dict_query())
        entries = list(result.scalars())
        entries.sort(key=lambda e: (-e.priority, -len(e.term)))
        self._dictionary = entries
        self._dict_last_updated = max(
            (e.updatedAt for e in entries), default=None
        )

    async def reload_if_updated(self, session: AsyncSession) -> None:
        """Check DB max updatedAt; reload dictionary if newer entries exist."""
        stmt = select(func.max(PronunciationEntry.updatedAt)).where(
            (PronunciationEntry.profileId == self._profile_id)
            | (PronunciationEntry.profileId.is_(None))
        )
        result = await session.execute(stmt)
        db_max: datetime | None = result.scalar_one_or_none()
        if db_max is None:
            return
        if self._dict_last_updated is None or db_max > self._dict_last_updated:
            result2 = await session.execute(self._dict_query())
            entries = list(result2.scalars())
            entries.sort(key=lambda e: (-e.priority, -len(e.term)))
            self._dictionary = entries
            self._dict_last_updated = db_max

    def process(self, zh_text: str) -> ProcessResult:
        if not zh_text:
            return ProcessResult(hanlo="", taibun="")
        protected = self._apply_dictionary(zh_text)
        hanlo_raw = str(self._hanlo.convert(protected))
        # strip protection markers before passing to taibun
        hanlo = _PROTECTED.sub(r"\1", hanlo_raw)
        taibun_text = str(self._taibun.get(hanlo)) if hanlo else ""
        return ProcessResult(hanlo=hanlo, taibun=taibun_text)

    def _apply_dictionary(self, text: str) -> str:
        for entry in self._dictionary:
            text = text.replace(entry.term, f"⟨{entry.replacement}⟩")
        return text
