from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config.settings import Settings, get_settings
from src.services.qa_service import QAService


def run_eval(
    questions_path: str | Path,
    report_path: str | Path,
    qa_service: QAService | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    qa = qa_service or QAService(cfg)
    questions = json.loads(Path(questions_path).read_text(encoding="utf-8"))

    hit = 0
    page_hit = 0
    page_total = 0
    rows: list[dict[str, Any]] = []

    for item in questions:
        question = item["question"]
        expected_doc = item.get("expected_doc_id")
        expected_filename = item.get("expected_filename")
        expected_page = item.get("expected_page_hint")

        retrieved, meta = qa.retrieve(question)
        retrieved_docs = [str(d.metadata.get("doc_id")) for d in retrieved]
        retrieved_files = [str(d.metadata.get("filename") or "") for d in retrieved]
        retrieved_pages = [
            int(d.metadata["page"])
            for d in retrieved
            if d.metadata.get("page") is not None
        ]

        doc_ok = False
        if expected_doc and expected_doc in retrieved_docs:
            doc_ok = True
        elif expected_filename and any(
            expected_filename.lower() in (f or "").lower() for f in retrieved_files
        ):
            doc_ok = True
        if doc_ok:
            hit += 1

        page_ok = None
        if expected_page is not None:
            page_total += 1
            page_ok = int(expected_page) in retrieved_pages
            if page_ok:
                page_hit += 1

        answer = qa.ask(question, structured=True)
        rows.append(
            {
                "question": question,
                "expected_doc_id": expected_doc,
                "expected_filename": expected_filename,
                "expected_page_hint": expected_page,
                "hit_doc": doc_ok,
                "hit_page": page_ok,
                "retrieved_doc_ids": retrieved_docs,
                "retrieved_files": retrieved_files,
                "retrieved_pages": retrieved_pages,
                "final_answer": answer.final_answer if hasattr(answer, "final_answer") else str(answer),
                "route_reason": meta.get("route").reason if meta.get("route") else "",
            }
        )

    n = max(len(questions), 1)
    metrics = {
        "total": len(questions),
        "hit_at_k": hit / n,
        "citation_page_hit_rate": (page_hit / page_total) if page_total else None,
        "page_eval_count": page_total,
        "top_k": cfg.top_k,
    }

    report = Path(report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Enterprise RAG Eval Report",
        "",
        f"- total questions: {metrics['total']}",
        f"- hit@{cfg.top_k}: {metrics['hit_at_k']:.2%}",
        f"- citation page hit rate: {metrics['citation_page_hit_rate'] if metrics['citation_page_hit_rate'] is not None else 'N/A'}",
        "",
        "## Details",
        "",
    ]
    for i, row in enumerate(rows, 1):
        lines.append(f"### Q{i}. {row['question']}")
        lines.append(f"- expected_doc_id: `{row['expected_doc_id']}`")
        lines.append(f"- hit_doc: {row['hit_doc']}")
        lines.append(f"- hit_page: {row['hit_page']}")
        lines.append(f"- retrieved_doc_ids: {row['retrieved_doc_ids']}")
        lines.append(f"- answer: {row['final_answer'][:300]}")
        lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")

    return {"metrics": metrics, "rows": rows, "report_path": str(report)}
