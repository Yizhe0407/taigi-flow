import re
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worker.db.models import PronunciationEntry

_HANLOFLOW_DIR = Path(__file__).resolve().parents[2] / "vendor" / "hanloflow"
if str(_HANLOFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_HANLOFLOW_DIR))

from converter import TaigiConverter  # type: ignore[import-untyped]  # noqa: E402
from taibun import Converter  # noqa: E402

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
        self._hanlo = TaigiConverter()
        self._taibun = Converter(system="Tailo", format="mark")

    async def load_dictionary(self) -> None:
        if self._db_session is None:
            self._dict_loaded = True
            return
        stmt = select(PronunciationEntry).where(
            (PronunciationEntry.profileId == self._profile_id)
            | (PronunciationEntry.profileId.is_(None))
        )
        result = await self._db_session.execute(stmt)
        entries = list(result.scalars().all())
        entries.sort(key=lambda e: (-e.priority, -len(e.term)))
        self._dictionary = entries
        self._dict_loaded = True

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
