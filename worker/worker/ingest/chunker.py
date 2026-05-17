from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_MAX_CHARS = 500
_OVERLAP = 50


@dataclass
class Chunk:
    content: str
    metadata: dict[str, object]


def chunk_file(file_path: str) -> list[Chunk]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix == ".docx":
        text = _extract_docx(path)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    paragraphs = _split_paragraphs(text)
    return _window_chunks(paragraphs, path.name)


def _extract_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        pages.append(t)
    return "\n\n".join(pages)


def _split_paragraphs(text: str) -> list[str]:
    paras = re.split(r"\n{2,}", text)
    return [p.strip() for p in paras if p.strip()]


def _window_chunks(paragraphs: list[str], source: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    current = ""
    idx = 0

    for para in paragraphs:
        if len(current) + len(para) + 1 <= _MAX_CHARS:
            current = (current + "\n\n" + para).lstrip()
        else:
            if current:
                chunks.append(
                    Chunk(content=current, metadata={"source": source, "chunk": idx})
                )
                idx += 1
                # overlap: keep trailing chars of previous chunk
                current = current[-_OVERLAP:] + "\n\n" + para if _OVERLAP else para
            else:
                # single paragraph exceeds max — hard split
                for i in range(0, len(para), _MAX_CHARS - _OVERLAP):
                    piece = para[i : i + _MAX_CHARS]
                    chunks.append(
                        Chunk(
                            content=piece,
                            metadata={"source": source, "chunk": idx},
                        )
                    )
                    idx += 1
                current = ""

    if current.strip():
        chunks.append(Chunk(content=current, metadata={"source": source, "chunk": idx}))

    return chunks
