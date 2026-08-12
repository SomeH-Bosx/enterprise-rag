"""Generate evaluation/reranker_compare.md (baseline dense vs DashScope rerank path)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.generation.llm_gateway import invoke_text
from src.generation.prompts.templates import build_context, build_simple_prompt
from src.services.ingest_service import IngestService
from src.services.qa_service import QAService


def _summarize(docs):
    rows = []
    for d in docs:
        rows.append(
            {
                "chunk_id": d.metadata.get("chunk_id"),
                "filename": d.metadata.get("filename"),
                "rerank_score": d.metadata.get("rerank_score"),
                "rerank_rank": d.metadata.get("rerank_rank"),
                "reranker": d.metadata.get("reranker"),
                "snippet": (d.page_content or "")[:180].replace("\n", " "),
            }
        )
    return rows


def _answer(docs, question, settings) -> str:
    try:
        return invoke_text(build_simple_prompt(build_context(docs), question), settings)
    except Exception as exc:  # noqa: BLE001
        return f"[LLM unavailable: {exc}]"


def main() -> None:
    setup_logging()
    get_settings.cache_clear()
    settings = get_settings()
    settings.use_reranker = True
    settings.reranker_backend = "dashscope"

    ingest = IngestService(settings)
    for pdf in sorted((ROOT / "data" / "samples").glob("*.pdf")):
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

    baseline_docs, baseline_meta = qa.retrieve(question, use_reranker=False, naive=True)
    baseline_answer = _answer(baseline_docs, question, settings)

    def _fake_call(**kwargs):
        docs = kwargs.get("documents") or []
        scored = []
        for i, text in enumerate(docs):
            low = (text or "").lower()
            score = 0.05
            if "p95" in low or "latency" in low or "200 milliseconds" in low:
                score += 0.9
            if "nebula" in low:
                score += 0.2
            scored.append({"index": i, "relevance_score": score})
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return SimpleNamespace(status_code=200, output={"results": scored})

    api_mode = "live" if settings.dashscope_api_key.strip() else "mocked"
    if api_mode == "mocked":
        with patch("dashscope.TextReRank.call", side_effect=_fake_call):
            rerank_docs, rerank_meta = qa.retrieve_with_rerank(question)
    else:
        rerank_docs, rerank_meta = qa.retrieve_with_rerank(question)
    rerank_answer = _answer(rerank_docs, question, settings)

    out_dir = ROOT / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "reranker_compare.md"

    baseline_ids = [d.metadata.get("chunk_id") for d in baseline_docs]
    rerank_ids = [d.metadata.get("chunk_id") for d in rerank_docs]

    lines = [
        "# Reranker Compare (Phase2 DashScope Upgrade)",
        "",
        f"- Question: **{question}**",
        f"- DashScope mode: `{api_mode}`",
        f"- Backend setting: `{settings.reranker_backend}`",
        f"- Model: `{settings.dashscope_rerank_model}`",
        "",
        "## Baseline",
        "",
        "Retriever directly takes Top-K (no rerank).",
        "",
        f"- meta: `{json.dumps(baseline_meta, ensure_ascii=False)}`",
        "",
        "### Retrieved chunks",
        "",
        "```json",
        json.dumps(_summarize(baseline_docs), ensure_ascii=False, indent=2),
        "```",
        "",
        "### Final answer",
        "",
        baseline_answer,
        "",
        "## Reranker",
        "",
        "Retriever Top-20 → DashScope Reranker → Top-5 → LLM",
        "",
        f"- meta: `{json.dumps(rerank_meta, ensure_ascii=False)}`",
        "",
        "### Retrieved chunks",
        "",
        "```json",
        json.dumps(_summarize(rerank_docs), ensure_ascii=False, indent=2),
        "```",
        "",
        "### Final answer",
        "",
        rerank_answer,
        "",
        "## Diff summary",
        "",
        f"- Baseline chunk_ids: `{baseline_ids}`",
        f"- Rerank chunk_ids: `{rerank_ids}`",
        f"- Order changed: **{baseline_ids != rerank_ids}**",
        "",
        "## Typical case",
        "",
        "For latency SLO questions, rerank should prioritize chunks containing "
        "`p95` / `latency` / `200 milliseconds` over cafeteria/parking noise.",
        "",
        "## Notes",
        "",
        "- If `DASHSCOPE_API_KEY` is empty, this report uses a mocked DashScope response "
        "so CI/local runs still produce a comparable artifact.",
        "- Set a real key in `.env` and re-run for live semantic rerank scores.",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} (dashscope_mode={api_mode})")


if __name__ == "__main__":
    main()
