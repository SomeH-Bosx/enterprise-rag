"""Tests for explicit Office conversion step (mocked engines)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.ingestion.office_convert import needs_legacy_conversion, prepare_for_load
from src.services.exceptions import IngestError


def test_needs_legacy_conversion():
    assert needs_legacy_conversion("a.ppt")
    assert needs_legacy_conversion("a.doc")
    assert not needs_legacy_conversion("a.pptx")
    assert not needs_legacy_conversion("a.docx")
    assert not needs_legacy_conversion("a.pdf")


def test_modern_format_skips_convert(tmp_path: Path):
    src = tmp_path / "deck.pptx"
    src.write_bytes(b"fake-pptx")
    outcome = prepare_for_load(src, work_dir=tmp_path / "_converted")
    assert outcome.converted is False
    assert outcome.engine == "none"
    assert outcome.load_path == src
    assert any(s.get("step") == "convert" and s.get("status") == "skipped" for s in outcome.steps)


def test_ppt_convert_via_mocked_office_com(tmp_path: Path):
    src = tmp_path / "legacy.ppt"
    src.write_bytes(b"fake-ppt")
    out_dir = tmp_path / "_converted"

    def _fake_com(src_path: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"converted-pptx")

    with patch("src.ingestion.office_convert._convert_ppt_via_powerpoint_com", side_effect=_fake_com):
        outcome = prepare_for_load(src, work_dir=out_dir)

    assert outcome.converted is True
    assert outcome.engine == "powerpoint_com"
    assert outcome.from_type == "ppt"
    assert outcome.to_type == "pptx"
    assert outcome.load_path.exists()
    convert_step = next(s for s in outcome.steps if s.get("step") == "convert")
    assert convert_step["status"] == "done"
    assert convert_step["engine"] == "powerpoint_com"


def test_ppt_convert_falls_back_to_soffice(tmp_path: Path):
    src = tmp_path / "legacy.ppt"
    src.write_bytes(b"fake-ppt")
    out_dir = tmp_path / "_converted"

    def _fail_com(*_a, **_k):
        raise RuntimeError("no powerpoint")

    def _fake_soffice(path: Path, *, target_ext: str, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        produced = out_dir / f"{path.stem}.{target_ext}"
        produced.write_bytes(b"from-soffice")
        return produced

    with (
        patch("src.ingestion.office_convert._convert_ppt_via_powerpoint_com", side_effect=_fail_com),
        patch("src.ingestion.office_convert._convert_via_soffice", side_effect=_fake_soffice),
    ):
        outcome = prepare_for_load(src, work_dir=out_dir)

    assert outcome.converted is True
    assert outcome.engine == "soffice"
    convert_step = next(s for s in outcome.steps if s.get("step") == "convert")
    assert convert_step["status"] == "done"
    assert convert_step.get("note") == "fallback_after_office_com_failed"


def test_ppt_convert_fails_clearly(tmp_path: Path):
    src = tmp_path / "legacy.ppt"
    src.write_bytes(b"fake-ppt")

    with (
        patch(
            "src.ingestion.office_convert._convert_ppt_via_powerpoint_com",
            side_effect=RuntimeError("no office"),
        ),
        patch(
            "src.ingestion.office_convert._convert_via_soffice",
            side_effect=RuntimeError("no soffice"),
        ),
        pytest.raises(IngestError, match="Convert ppt→pptx failed"),
    ):
        prepare_for_load(src, work_dir=tmp_path / "_converted")
