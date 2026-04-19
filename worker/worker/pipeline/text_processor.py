import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.db.models import PronunciationEntry

_HANLOFLOW_DIR = Path(__file__).resolve().parents[2] / "vendor" / "hanloflow"
if str(_HANLOFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_HANLOFLOW_DIR))

from converter import TaigiConverter  # type: ignore[import-untyped]  # noqa: E402
import taibun.taibun as _taibun_module  # noqa: E402
from taibun import Converter  # noqa: E402

# Patch chars missing from taibun.
# word_dict (words.msgpack) = char → romanization str; checked by WordDict.__contains__
# prons_dict (prons.msgpack) = char → list[str]; used for variant lookups
# Both must be patched before any Converter is created.
_TAIBUN_PATCHES: dict[str, str] = {
    "妳": "lí",
    "您": "lín",
    "她": "i",
    "它": "i",
    "嗎": "ma",
    "嘸": "bô",
    "呣": "m̄",
    "咧": "leh",
    "囉": "lô",
    "啦": "la",
    "喔": "oh",
    "欸": "eh",
    "唷": "ioh",
}
for _ch, _rom in _TAIBUN_PATCHES.items():
    _taibun_module.word_dict.setdefault(_ch, _rom)
    _taibun_module.prons_dict.setdefault(_ch, [_rom])

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
        self._dict_loaded = False
        self._dict_last_updated: datetime | None = None
        self._hanlo = TaigiConverter()
        self._taibun = Converter(system="Tailo", format="number")

    def _dict_query(self) -> object:
        return select(PronunciationEntry).where(
            (PronunciationEntry.profileId == self._profile_id)
            | (PronunciationEntry.profileId.is_(None))
        )

    async def load_dictionary(self) -> None:
        if self._db_session is None:
            self._dict_loaded = True
            return
        result = await self._db_session.execute(self._dict_query())
        entries = list(result.scalars().all())
        entries.sort(key=lambda e: (-e.priority, -len(e.term)))
        self._dictionary = entries
        self._dict_last_updated = max(
            (e.updatedAt for e in entries), default=None
        )
        self._dict_loaded = True

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
            entries = list(result2.scalars().all())
            entries.sort(key=lambda e: (-e.priority, -len(e.term)))
            self._dictionary = entries
            self._dict_last_updated = db_max

    def process(self, zh_text: str) -> ProcessResult:
        if not zh_text:
            return ProcessResult(hanlo="", taibun="")
        protected = self._apply_dictionary(zh_text)
        hanlo_raw: str = self._hanlo.convert(protected)  # type: ignore[assignment]
        # strip protection markers before passing to taibun
        hanlo = _PROTECTED.sub(r"\1", hanlo_raw)
        taibun_text: str = self._taibun.get(hanlo) if hanlo else ""
        return ProcessResult(hanlo=hanlo, taibun=taibun_text)

    def _apply_dictionary(self, text: str) -> str:
        for entry in self._dictionary:
            text = text.replace(entry.term, f"⟨{entry.replacement}⟩")
        return text
