"""显式 legacy Office 转换（.ppt→.pptx、.doc→.docx）。

主引擎：Microsoft Office COM（演示机通常已装 Office）。
回退：LibreOffice soffice。
转换是一等公民流水线步骤，会暴露给 API/UI。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.services.exceptions import IngestError

# PowerPoint SaveAs: Open XML Presentation
_PP_SAVE_AS_OPENXML = 24
# Word SaveAs: Word default Document (docx)
_WD_FORMAT_XML_DOCUMENT = 12

_LEGACY_TARGETS: dict[str, str] = {
    ".ppt": ".pptx",
    ".doc": ".docx",
}


@dataclass
class ConversionOutcome:
    """Result of the optional convert step before loading."""

    original_path: Path
    load_path: Path
    converted: bool
    from_type: str
    to_type: str
    engine: str  # none | powerpoint_com | word_com | soffice
    output_path: str | None = None
    elapsed_ms: float = 0.0
    steps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "converted": self.converted,
            "from_type": self.from_type,
            "to_type": self.to_type,
            "engine": self.engine,
            "original_path": str(self.original_path),
            "load_path": str(self.load_path),
            "output_path": self.output_path,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "steps": self.steps,
        }


def needs_legacy_conversion(path: str | Path) -> bool:
    return Path(path).suffix.lower() in _LEGACY_TARGETS


def prepare_for_load(path: str | Path, *, work_dir: str | Path | None = None) -> ConversionOutcome:
    """
    If legacy .ppt/.doc: convert to .pptx/.docx (explicit step), then return path to load.
    Otherwise: no-op conversion step.
    """
    src = Path(path)
    if not src.exists():
        raise IngestError(f"File not found: {src}")

    suffix = src.suffix.lower()
    from_type = suffix.lstrip(".") or "unknown"
    steps: list[dict[str, Any]] = [
        {
            "step": "detect",
            "status": "done",
            "file_type": from_type,
            "filename": src.name,
        }
    ]

    target_suffix = _LEGACY_TARGETS.get(suffix)
    if not target_suffix:
        steps.append(
            {
                "step": "convert",
                "status": "skipped",
                "reason": "modern_format_no_conversion_needed",
                "from_type": from_type,
                "to_type": from_type,
            }
        )
        return ConversionOutcome(
            original_path=src,
            load_path=src,
            converted=False,
            from_type=from_type,
            to_type=from_type,
            engine="none",
            steps=steps,
        )

    to_type = target_suffix.lstrip(".")
    out_root = Path(work_dir) if work_dir else src.parent / "_converted"
    out_root.mkdir(parents=True, exist_ok=True)
    dest = out_root / f"{src.stem}{target_suffix}"

    steps.append(
        {
            "step": "convert",
            "status": "started",
            "from_type": from_type,
            "to_type": to_type,
            "preferred_engine": "microsoft_office_com",
            "fallback_engine": "libreoffice_soffice",
        }
    )

    errors: list[str] = []
    t0 = time.perf_counter()

    # 1) Microsoft Office COM (preferred for demo)
    try:
        if suffix == ".ppt":
            _convert_ppt_via_powerpoint_com(src, dest)
            engine = "powerpoint_com"
        else:
            _convert_doc_via_word_com(src, dest)
            engine = "word_com"
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if not dest.exists():
            raise IngestError(f"Office COM reported success but output missing: {dest}")
        steps[-1].update(
            {
                "status": "done",
                "engine": engine,
                "output": dest.name,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        )
        return ConversionOutcome(
            original_path=src,
            load_path=dest,
            converted=True,
            from_type=from_type,
            to_type=to_type,
            engine=engine,
            output_path=str(dest),
            elapsed_ms=elapsed_ms,
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"office_com: {exc}")

    # 2) LibreOffice fallback
    try:
        converted = _convert_via_soffice(src, target_ext=to_type, out_dir=out_root)
        # Normalize name next to cache
        if converted.resolve() != dest.resolve():
            shutil.copy2(converted, dest)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        steps[-1].update(
            {
                "status": "done",
                "engine": "soffice",
                "output": dest.name,
                "elapsed_ms": round(elapsed_ms, 2),
                "note": "fallback_after_office_com_failed",
                "prior_errors": errors,
            }
        )
        return ConversionOutcome(
            original_path=src,
            load_path=dest,
            converted=True,
            from_type=from_type,
            to_type=to_type,
            engine="soffice",
            output_path=str(dest),
            elapsed_ms=elapsed_ms,
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"soffice: {exc}")

    elapsed_ms = (time.perf_counter() - t0) * 1000
    steps[-1].update(
        {
            "status": "failed",
            "elapsed_ms": round(elapsed_ms, 2),
            "errors": errors,
        }
    )
    detail = " | ".join(errors) if errors else "unknown"
    raise IngestError(
        f"Convert {from_type}→{to_type} failed. "
        f"Install Microsoft Office (pywin32) or LibreOffice, "
        f"or re-upload as .{to_type}. Details: {detail}"
    )


def _require_win32com():
    try:
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise IngestError(
            "pywin32 is required for Microsoft Office conversion on Windows. "
            "Install with: pip install pywin32"
        ) from exc
    return win32com.client


def _convert_ppt_via_powerpoint_com(src: Path, dest: Path) -> None:
    """Explicit step: PowerPoint opens .ppt and SaveAs .pptx."""
    win32com_client = _require_win32com()
    app = win32com_client.Dispatch("PowerPoint.Application")
    try:
        try:
            app.Visible = 1
        except Exception:
            pass
        presentation = app.Presentations.Open(str(src.resolve()), WithWindow=False)
        try:
            if dest.exists():
                dest.unlink()
            # SaveAs(FileName, FileFormat)
            presentation.SaveAs(str(dest.resolve()), _PP_SAVE_AS_OPENXML)
        finally:
            presentation.Close()
    finally:
        app.Quit()


def _convert_doc_via_word_com(src: Path, dest: Path) -> None:
    """Explicit step: Word opens .doc and SaveAs .docx."""
    win32com_client = _require_win32com()
    word = win32com_client.Dispatch("Word.Application")
    word.Visible = False
    try:
        document = word.Documents.Open(str(src.resolve()))
        try:
            if dest.exists():
                dest.unlink()
            document.SaveAs2(str(dest.resolve()), FileFormat=_WD_FORMAT_XML_DOCUMENT)
        finally:
            document.Close(False)
    finally:
        word.Quit()


def _convert_via_soffice(path: Path, *, target_ext: str, out_dir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("soffice.exe")
    if not soffice:
        # Common Windows install locations
        for candidate in (
            Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
        ):
            if candidate.exists():
                soffice = str(candidate)
                break
    if not soffice:
        raise IngestError("LibreOffice soffice not found on PATH or default install paths")

    out_dir.mkdir(parents=True, exist_ok=True)
    # Use a clean temp outdir to avoid name collisions, then return produced file
    tmp_out = Path(tempfile.mkdtemp(prefix="rag_soffice_", dir=str(out_dir)))
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        target_ext,
        "--outdir",
        str(tmp_out),
        str(path.resolve()),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if proc.returncode != 0:
        raise IngestError(f"soffice convert failed: {(proc.stderr or proc.stdout or '').strip()}")

    converted = tmp_out / f"{path.stem}.{target_ext}"
    if not converted.exists():
        matches = list(tmp_out.glob(f"*.{target_ext}"))
        if not matches:
            raise IngestError("soffice produced no output file")
        converted = matches[0]
    return converted
