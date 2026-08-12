"""Plain-text / Markdown loaders."""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

from src.ingestion.loaders._common import docs_or_fail, ensure_file


def load_txt(path: str | Path) -> list[Document]:
    return _load_text_file(path, file_type="txt", suffixes=(".txt",))


def load_md(path: str | Path) -> list[Document]:
    return _load_text_file(path, file_type="md", suffixes=(".md", ".markdown"))


def _load_text_file(
    path: str | Path,
    *,
    file_type: str,
    suffixes: tuple[str, ...],
) -> list[Document]:
    text_path = ensure_file(path, expected_suffixes=suffixes)
    raw = text_path.read_bytes()
    text = _decode_bytes(raw).strip()
    docs = [
        Document(
            page_content=text,
            metadata={
                "source": str(text_path),
                "filename": text_path.name,
                "file_type": file_type,
                "page": 0,
            },
        )
    ]
    return docs_or_fail(docs, label=file_type.upper())


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
