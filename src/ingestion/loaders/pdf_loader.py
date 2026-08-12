"""PDF loader with Markdown table serialization + optional OCR (Step3.6).

Keeps the same `load_pdf(path) -> list[Document]` contract.
Uses pdfplumber directly (still the Phase1 PDF engine family).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.ingestion.loaders._common import docs_or_fail, ensure_file
from src.ingestion.ocr import ocr_pdf_page_image, should_ocr_text
from src.ingestion.tables import pdfplumber_table_to_markdown
from src.services.exceptions import IngestError

logger = get_logger("pdf_loader")


def load_pdf(path: str | Path, settings: Settings | None = None) -> list[Document]:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise IngestError("pdfplumber is required for .pdf support") from exc

    cfg = settings or get_settings()
    pdf_path = ensure_file(path, expected_suffixes=(".pdf",))
    docs: list[Document] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_no = i + 1
            parts: list[str] = []
            table_count = 0
            ocr_status = "skipped_not_needed"
            ocr_detail = ""

            raw_text = (page.extract_text() or "").strip()
            if raw_text:
                parts.append(raw_text)

            if cfg.enable_table_serialization:
                try:
                    tables = page.extract_tables() or []
                except Exception as exc:  # noqa: BLE001
                    logger.warning("pdf_table_extract_failed", page=page_no, error=str(exc))
                    tables = []
                for table in tables:
                    md = pdfplumber_table_to_markdown(table)
                    if md:
                        parts.append(md)
                        table_count += 1
            else:
                # Legacy-ish: still append simple table cell text if serialization off
                try:
                    tables = page.extract_tables() or []
                except Exception:  # noqa: BLE001
                    tables = []
                for table in tables:
                    for row in table or []:
                        line = " | ".join(
                            str(c).strip() for c in row if c is not None and str(c).strip()
                        )
                        if line:
                            parts.append(line)

            body = "\n\n".join(p for p in parts if p).strip()

            if should_ocr_text(body, min_chars=cfg.ocr_min_text_chars):
                if cfg.enable_ocr:
                    ocr = ocr_pdf_page_image(page, cfg)
                    ocr_status = ocr.status
                    ocr_detail = ocr.detail
                    if ocr.text:
                        body = (body + "\n\n" + ocr.text).strip() if body else ocr.text
                else:
                    ocr_status = "skipped_disabled"
                    logger.info("ocr_skipped", page=page_no, reason="ENABLE_OCR=false")
            else:
                ocr_status = "skipped_not_needed"

            if not body:
                logger.info(
                    "pdf_page_empty",
                    page=page_no,
                    table_count=table_count,
                    ocr_status=ocr_status,
                    ocr_detail=ocr_detail,
                )
                continue

            meta: dict[str, Any] = {
                "source": str(pdf_path),
                "filename": pdf_path.name,
                "file_type": "pdf",
                "page": page_no,
                "table_count": table_count,
                "ocr_status": ocr_status,
                "ocr_detail": ocr_detail,
                "ocr_engine": "tesseract" if ocr_status == "applied" else "",
            }
            docs.append(Document(page_content=body, metadata=meta))

    return docs_or_fail(docs, label="PDF")
