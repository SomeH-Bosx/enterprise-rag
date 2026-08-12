"""Phase5 评测 runner：Recall@K + RAGAS-style 答案指标 + 报告。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.eval.ragas_lite import aggregate_ragas_style, score_row
from src.eval.recall import aggregate_recall, recall_hit
from src.services.qa_service import QAService

logger = get_logger("eval")


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("questions file must be a JSON list")
    return data


def run_eval(
    questions_path: str | Path,
    report_path: str | Path,
    qa_service: QAService | None = None,
    settings: Settings | None = None,
    *,
    skip_generation: bool = False,
    json_report_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    在标注题集上跑 Phase5 评测。

    - Recall@K：期望 filename / doc_id 出现在检索 Top-K
    - RAGAS-style：faithfulness / answer_relevancy / context_precision（+ must_include）
    """
    cfg = settings or get_settings()
    # Eval should not pollute conversation store
    cfg = cfg.model_copy(update={"use_conversation_memory": False})
    qa = qa_service or QAService(cfg)

    questions = load_questions(questions_path)
    rows: list[dict[str, Any]] = []
    recall_flags: list[bool] = []
    ragas_rows: list[dict[str, Any]] = []
    page_hit = 0
    page_total = 0
    started = time.perf_counter()

    for idx, item in enumerate(questions, start=1):
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        expected_doc = item.get("expected_doc_id")
        expected_filename = item.get("expected_filename")
        expected_page = item.get("expected_page_hint")
        ground_truth = item.get("ground_truth")
        must_include = item.get("must_include") or []

        t0 = time.perf_counter()
        retrieved, meta = qa.retrieve(question, use_reranker=cfg.use_reranker)
        retrieve_ms = (time.perf_counter() - t0) * 1000

        retrieved_docs = [str(d.metadata.get("doc_id")) for d in retrieved]
        retrieved_files = [str(d.metadata.get("filename") or "") for d in retrieved]
        retrieved_pages = [
            int(d.metadata["page"])
            for d in retrieved
            if d.metadata.get("page") is not None
        ]
        contexts = [d.page_content or "" for d in retrieved]

        doc_ok = recall_hit(
            retrieved_files=retrieved_files,
            retrieved_doc_ids=retrieved_docs,
            expected_filename=expected_filename,
            expected_doc_id=str(expected_doc) if expected_doc else None,
        )
        recall_flags.append(doc_ok)

        page_ok = None
        if expected_page is not None:
            page_total += 1
            page_ok = int(expected_page) in retrieved_pages
            if page_ok:
                page_hit += 1

        answer_text = ""
        gen_ms = 0.0
        if not skip_generation:
            t1 = time.perf_counter()
            answer = qa.ask(question, structured=False)
            gen_ms = (time.perf_counter() - t1) * 1000
            if isinstance(answer, dict):
                answer_text = str(answer.get("answer") or answer.get("final_answer") or "")
            else:
                answer_text = getattr(answer, "final_answer", str(answer))

            ragas = score_row(
                answer=answer_text,
                question=question,
                contexts=contexts,
                ground_truth=str(ground_truth) if ground_truth else None,
                must_include=must_include,
                context_hit=doc_ok,
            )
            ragas_rows.append(ragas)
        else:
            ragas = {
                "faithfulness": None,
                "answer_relevancy": None,
                "context_precision": 1.0 if doc_ok else 0.0,
                "must_include_pass": None,
            }

        row = {
            "id": item.get("id") or f"q{idx}",
            "question": question,
            "expected_doc_id": expected_doc,
            "expected_filename": expected_filename,
            "expected_page_hint": expected_page,
            "ground_truth": ground_truth,
            "hit_doc": doc_ok,
            "hit_page": page_ok,
            "retrieved_doc_ids": retrieved_docs,
            "retrieved_files": retrieved_files,
            "retrieved_pages": retrieved_pages,
            "retrieve_ms": round(retrieve_ms, 2),
            "generate_ms": round(gen_ms, 2),
            "final_answer": answer_text[:500],
            "mode": meta.get("mode"),
            "ragas": ragas,
        }
        rows.append(row)
        logger.info(
            "eval_item_done",
            idx=idx,
            hit_doc=doc_ok,
            retrieve_ms=round(retrieve_ms, 2),
            generate_ms=round(gen_ms, 2),
        )

    recall_metrics = aggregate_recall(recall_flags)
    ragas_metrics = (
        aggregate_ragas_style(ragas_rows)
        if not skip_generation
        else {"skipped": True, "backend": "ragas_lite"}
    )
    metrics = {
        "total": recall_metrics["total"],
        "recall_at_k": recall_metrics["recall_at_k"],
        "hit_at_k": recall_metrics["recall_at_k"],  # alias for older CLI consumers
        "hits": recall_metrics["hits"],
        "citation_page_hit_rate": (page_hit / page_total) if page_total else None,
        "page_eval_count": page_total,
        "top_k": cfg.top_k,
        "recall_top_n": cfg.recall_top_n,
        "use_reranker": cfg.use_reranker,
        "use_bm25": cfg.use_bm25,
        "skip_generation": skip_generation,
        "ragas": ragas_metrics,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }

    report = Path(report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_render_markdown(metrics, rows, cfg), encoding="utf-8")

    payload = {"metrics": metrics, "rows": rows, "report_path": str(report)}
    if json_report_path is not None:
        jpath = Path(json_report_path)
        jpath.parent.mkdir(parents=True, exist_ok=True)
        jpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["json_report_path"] = str(jpath)

    return payload


def _render_markdown(metrics: dict[str, Any], rows: list[dict[str, Any]], cfg: Settings) -> str:
    ragas = metrics.get("ragas") or {}
    lines = [
        "# Enterprise RAG — Phase5 评测报告",
        "",
        "## 汇总",
        "",
        f"- 题目总数: **{metrics.get('total')}**",
        f"- Recall@{cfg.top_k}: **{float(metrics.get('recall_at_k') or 0):.2%}** "
        f"({metrics.get('hits')}/{metrics.get('total')})",
        f"- 引用页码命中率: "
        f"**{metrics['citation_page_hit_rate'] if metrics.get('citation_page_hit_rate') is not None else 'N/A'}**",
        f"- use_reranker: `{metrics.get('use_reranker')}` · use_bm25: `{metrics.get('use_bm25')}`",
        f"- elapsed_ms: `{metrics.get('elapsed_ms')}`",
        "",
        "### RAGAS-style 指标",
        "",
    ]
    if ragas.get("skipped"):
        lines.append("- 已跳过生成（`--skip-generation`）；未计算 RAGAS-style")
    else:
        lines.extend(
            [
                f"- backend: `{ragas.get('backend')}`",
                f"- faithfulness: **{ragas.get('faithfulness')}**",
                f"- answer_relevancy: **{ragas.get('answer_relevancy')}**",
                f"- context_precision: **{ragas.get('context_precision')}**",
                f"- must_include_pass_rate: **{ragas.get('must_include_pass_rate')}**",
                "",
                "> 说明：以上为轻量 RAGAS 概念代理（token 重叠），可离线复现，无需安装完整 `ragas` 包。",
            ]
        )
    lines.extend(["", "## 明细", ""])
    for i, row in enumerate(rows, 1):
        lines.append(f"### Q{i}. {row['question']}")
        lines.append(f"- id: `{row.get('id')}`")
        lines.append(f"- expected_filename: `{row.get('expected_filename')}`")
        lines.append(f"- hit_doc (Recall): **{row.get('hit_doc')}**")
        lines.append(f"- hit_page: {row.get('hit_page')}")
        lines.append(f"- retrieved_files: {row.get('retrieved_files')}")
        if row.get("ground_truth"):
            lines.append(f"- ground_truth: {row.get('ground_truth')}")
        rag = row.get("ragas") or {}
        if rag.get("faithfulness") is not None:
            lines.append(
                f"- ragas_lite: faith={rag.get('faithfulness')} · "
                f"relev={rag.get('answer_relevancy')} · "
                f"ctx_prec={rag.get('context_precision')} · "
                f"must_include={rag.get('must_include_pass')}"
            )
        ans = row.get("final_answer") or ""
        if ans:
            lines.append(f"- answer: {ans[:400]}")
        lines.append("")
    return "\n".join(lines)
