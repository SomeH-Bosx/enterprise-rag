"""Unified multi-format Document Loader facade.

Architecture:
  File Upload
    → Type Detection
    → [Convert legacy .ppt/.doc → .pptx/.docx]  (explicit Office/LibreOffice step)
    → Format Loader
    → Document[]
    → Splitter → Embed → Vector DB

Supported today: pdf, doc, docx, ppt, pptx, md, txt
Extension point: register another suffix in LOADER_REGISTRY (e.g. xlsx, html).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from langchain_core.documents import Document

from src.ingestion.loaders.docx_loader import load_doc, load_docx
from src.ingestion.loaders.pdf_loader import load_pdf
from src.ingestion.loaders.ppt_loader import load_ppt, load_pptx
from src.ingestion.loaders.text_loader import load_md, load_txt
from src.services.exceptions import IngestError

LoaderFn = Callable[[str | Path], list[Document]]

# suffix → loader (lowercase, with leading dot)
LOADER_REGISTRY: dict[str, LoaderFn] = {
    ".pdf": load_pdf,
    ".doc": load_doc,
    ".docx": load_docx,
    ".ppt": load_ppt,
    ".pptx": load_pptx,
    ".md": load_md,
    ".markdown": load_md,
    ".txt": load_txt,
}

SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(sorted({ext.lstrip(".") for ext in LOADER_REGISTRY}))
SUPPORTED_SUFFIXES: tuple[str, ...] = tuple(sorted(LOADER_REGISTRY.keys()))


def detect_file_type(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if not suffix:
        raise IngestError("File has no extension; cannot detect type")
    if suffix not in LOADER_REGISTRY:
        raise IngestError(
            f"Unsupported file type {suffix!r}. "
            f"Supported: {', '.join(SUPPORTED_SUFFIXES)}"
        )
    return suffix.lstrip(".")


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in LOADER_REGISTRY


def register_loader(suffix: str, loader: LoaderFn) -> None:
    """Extension hook for future formats (xlsx, html, ...)."""
    key = suffix.lower()
    if not key.startswith("."):
        key = f".{key}"
    LOADER_REGISTRY[key] = loader


def load_document(path: str | Path) -> list[Document]:
    """Detect type and dispatch to the matching loader. Returns unified Document list."""
    file_path = Path(path)
    if not file_path.exists():
        raise IngestError(f"File not found: {file_path}")
    suffix = file_path.suffix.lower()
    loader = LOADER_REGISTRY.get(suffix)
    if loader is None:
        raise IngestError(
            f"Unsupported file type {suffix!r}. "
            f"Supported: {', '.join(SUPPORTED_SUFFIXES)}"
        )
    docs = loader(file_path)
    # Normalize common metadata without changing page_content.
    for doc in docs:
        meta = dict(doc.metadata or {})
        meta.setdefault("source", str(file_path))
        meta.setdefault("filename", file_path.name)
        meta.setdefault("file_type", suffix.lstrip("."))
        doc.metadata = meta
    return docs


__all__ = [
    "LOADER_REGISTRY",
    "SUPPORTED_EXTENSIONS",
    "SUPPORTED_SUFFIXES",
    "detect_file_type",
    "is_supported",
    "load_doc",
    "load_docx",
    "load_document",
    "load_md",
    "load_pdf",
    "load_ppt",
    "load_pptx",
    "load_txt",
    "register_loader",
]
