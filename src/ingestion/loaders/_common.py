"""各格式 Document Loader 的共享辅助函数。"""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

from src.services.exceptions import IngestError


def ensure_file(path: str | Path, *, expected_suffixes: tuple[str, ...]) -> Path:
    file_path = Path(path)
    if not file_path.exists():
        raise IngestError(f"File not found: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix not in expected_suffixes:
        raise IngestError(
            f"Unexpected extension {suffix!r} for this loader "
            f"(expected {', '.join(expected_suffixes)})"
        )
    return file_path


def docs_or_fail(docs: list[Document], *, label: str) -> list[Document]:
    cleaned = [d for d in docs if (d.page_content or "").strip()]
    if not cleaned:
        raise IngestError(f"{label} produced no extractable text")
    return cleaned
