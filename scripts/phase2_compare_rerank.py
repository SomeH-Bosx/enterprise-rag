"""Phase2 helper: compare dense-only vs dense+rerank chunk ordering."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.services.ingest_service import IngestService
from src.services.qa_service import QAService


def main() -> None:
    setup_logging()
    get_settings.cache_clear()
    settings = get_settings()
    ingest = IngestService(settings)
    samples = sorted((ROOT / "data" / "samples").glob("*.pdf"))
    if not samples:
        raise SystemExit("No sample PDFs found. Run scripts/make_sample_pdfs.py first.")
    for pdf in samples:
        ingest.ingest_pdf(pdf)

    qa = QAService(
        settings,
        vector_store=ingest.vector_store,
        bm25_store=ingest.bm25_store,
        registry=ingest.registry,
    )
    question = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What is the p95 latency SLO for Nebula Search Appliance?"
    )
    result = qa.compare_rerank(question)
    out = ROOT / "docs" / "retrieval_ablation.md"
    lines = [
        "# Retrieval Ablation (Phase2 Reranker)",
        "",
        f"Question: **{result['question']}**",
        "",
        "## Baseline: Dense Top-K (no rerank)",
        "",
        "```json",
        json.dumps(result["baseline_dense"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Dense Recall + CrossEncoder Rerank → Top-N",
        "",
        "```json",
        json.dumps(result["dense_plus_rerank"], ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
