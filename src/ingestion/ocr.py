"""可选 OCR：pytesseract + 系统 Tesseract（Step3.6，引擎 A）。

默认开启（`ENABLE_OCR=true`）。缺 pytesseract / Tesseract / Pillow 时，
调用方应跳过并打日志——入库不得因此硬失败。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings

logger = get_logger("ocr")

OcrStatus = Literal[
    "applied",
    "skipped_disabled",
    "skipped_unavailable",
    "skipped_not_needed",
    "failed",
]


@dataclass
class OcrResult:
    text: str
    status: OcrStatus
    engine: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "engine": self.engine,
            "detail": self.detail,
            "char_count": len(self.text or ""),
        }


def ocr_available() -> tuple[bool, str]:
    """Return (ok, reason). Does not raise."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False, "pytesseract_not_installed"
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return False, "pillow_not_installed"
    try:
        import pytesseract

        # Light probe — may fail if Tesseract binary missing
        _ = pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001
        return False, f"tesseract_unavailable:{exc}"
    return True, "ok"


def should_ocr_text(text: str, *, min_chars: int) -> bool:
    return len((text or "").strip()) < max(0, int(min_chars))


def ocr_pil_image(image: Any, settings: Settings | None = None) -> OcrResult:
    """Run Tesseract on a Pillow Image. Never raises to callers."""
    cfg = settings or get_settings()
    if not cfg.enable_ocr:
        return OcrResult(text="", status="skipped_disabled", detail="ENABLE_OCR=false")

    ok, reason = ocr_available()
    if not ok:
        logger.warning("ocr_skipped", reason=reason)
        return OcrResult(text="", status="skipped_unavailable", detail=reason)

    try:
        import pytesseract

        lang = (cfg.ocr_lang or "chi_sim+eng").strip() or "chi_sim+eng"
        text = pytesseract.image_to_string(image, lang=lang) or ""
        text = text.strip()
        logger.info("ocr_applied", chars=len(text), lang=lang)
        return OcrResult(
            text=text,
            status="applied",
            engine="tesseract",
            detail=f"lang={lang}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr_failed", error=str(exc))
        return OcrResult(text="", status="failed", engine="tesseract", detail=str(exc))


def ocr_pdf_page_image(page: Any, settings: Settings | None = None) -> OcrResult:
    """
    OCR a pdfplumber page by rendering to image.
    If rendering fails, skip with log (do not fail ingest).
    """
    cfg = settings or get_settings()
    if not cfg.enable_ocr:
        return OcrResult(text="", status="skipped_disabled", detail="ENABLE_OCR=false")

    try:
        # pdfplumber Page.to_image requires Pillow (+ rendering backend)
        page_image = page.to_image(resolution=int(cfg.ocr_dpi) or 200)
        pil = getattr(page_image, "original", None)
        if pil is None:
            logger.warning("ocr_skipped", reason="page_image_missing")
            return OcrResult(
                text="",
                status="skipped_unavailable",
                detail="page_image_missing",
            )
        return ocr_pil_image(pil, cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr_skipped", reason="render_failed", error=str(exc))
        return OcrResult(
            text="",
            status="skipped_unavailable",
            detail=f"render_failed:{exc}",
        )
