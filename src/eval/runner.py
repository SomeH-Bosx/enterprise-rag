"""Phase5 评测 runner：Recall@K + RAGAS-style 答案指标 + 报告。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.eval.ragas_lite import aggregate_ragas_style, score_row
from src.eval.recall import aggregate_recall, recall_hit, strict_citation_hit
from src.retrieval.hybrid import resolve_retrieval_mode
from src.services.qa_service import QAService

logger = get_logger("eval")


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("questions file must be a JSON list")
    return data


def _slice_top_k(docs: list[Document], top_k: int) -> list[Document]:
    k = max(1, int(top_k))
    return list(docs[:k])


def _chunk_ids(docs: list[Document]) -> list[str]:
    return [str(d.metadata.get("chunk_id") or "") for d in docs]


def _score_docs(
    retrieved: list[Document],
    item: dict[str, Any],
    *,
    top_k: int,
) -> dict[str, Any]:
    """Score filename/page hit on retrieved[:top_k]. Recall definition unchanged."""
    ranked = _slice_top_k(retrieved, top_k)
    retrieved_docs = [str(d.metadata.get("doc_id")) for d in ranked]
    retrieved_files: list[str] = []
    retrieved_pages: list[int] = []
    aligned_pages: list[int | None] = []
    for d in ranked:
        retrieved_files.append(str(d.metadata.get("filename") or ""))
        raw_page = d.metadata.get("page")
        if raw_page is None:
            aligned_pages.append(None)
            continue
        page_i = int(raw_page)
        retrieved_pages.append(page_i)
        aligned_pages.append(page_i)
    expected_doc = item.get("expected_doc_id")
    expected_filename = item.get("expected_filename")
    expected_page = item.get("expected_page_hint")
    doc_ok = recall_hit(
        retrieved_files=retrieved_files,
        retrieved_doc_ids=retrieved_docs,
        expected_filename=expected_filename,
        expected_doc_id=str(expected_doc) if expected_doc else None,
    )
    page_ok = None
    page_strict = None
    if expected_page is not None:
        page_ok = int(expected_page) in retrieved_pages
        page_strict = strict_citation_hit(
            retrieved_files=retrieved_files,
            retrieved_pages=aligned_pages,
            expected_filename=expected_filename,
            expected_page=expected_page,
        )
    return {
        "hit_doc": doc_ok,
        "hit_page": page_ok,
        "hit_page_strict": page_strict,
        "retrieved_doc_ids": retrieved_docs,
        "retrieved_files": retrieved_files,
        "retrieved_pages": retrieved_pages,
        "contexts": [d.page_content or "" for d in ranked],
    }


def _config_fields(
    *,
    retrieval_mode: str,
    recall_k: int,
    candidate_count: int,
    top_k: int,
    use_reranker: bool,
) -> dict[str, Any]:
    """Fields that describe what actually ran (not leftover Settings)."""
    use_bm25 = retrieval_mode in {"hybrid", "bm25"}
    return {
        "retrieval_mode": retrieval_mode,
        "recall_k": recall_k,
        "candidate_count": candidate_count,
        "top_k": top_k,
        "use_reranker": use_reranker,
        "use_bm25": use_bm25,
    }


def _write_reports(
    metrics: dict[str, Any],
    rows: list[dict[str, Any]],
    cfg: Settings,
    report_path: str | Path,
    json_report_path: str | Path | None,
) -> dict[str, Any]:
    report = Path(report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_render_markdown(metrics, rows, cfg), encoding="utf-8")
    payload: dict[str, Any] = {"metrics": metrics, "rows": rows, "report_path": str(report)}
    if json_report_path is not None:
        jpath = Path(json_report_path)
        jpath.parent.mkdir(parents=True, exist_ok=True)
        jpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["json_report_path"] = str(jpath)
    return payload


def _aggregate_rows(
    rows: list[dict[str, Any]],
    *,
    elapsed_ms: float,
    skip_generation: bool,
    ragas_rows: list[dict[str, Any]] | None = None,
    extra_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recall_metrics = aggregate_recall(bool(r.get("hit_doc")) for r in rows)
    page_vals = [r.get("hit_page") for r in rows if r.get("hit_page") is not None]
    page_total = len(page_vals)
    page_hit = sum(1 for v in page_vals if v)
    strict_vals = [r.get("hit_page_strict") for r in rows if r.get("hit_page_strict") is not None]
    strict_total = len(strict_vals)
    strict_hit = sum(1 for v in strict_vals if v)
    ragas_metrics = (
        aggregate_ragas_style(ragas_rows or [])
        if not skip_generation
        else {"skipped": True, "backend": "ragas_lite"}
    )
    cfg_from_rows = {}
    if rows:
        cfg_from_rows = {
            "retrieval_mode": rows[0].get("retrieval_mode"),
            "recall_k": rows[0].get("recall_k"),
            "candidate_count": max(int(r.get("candidate_count") or 0) for r in rows),
            "top_k": rows[0].get("top_k"),
            "use_reranker": rows[0].get("use_reranker"),
            "use_bm25": rows[0].get("use_bm25"),
        }
    metrics: dict[str, Any] = {
        "total": recall_metrics["total"],
        "recall_at_k": recall_metrics["recall_at_k"],
        "hit_at_k": recall_metrics["recall_at_k"],
        "hit_at_k_is_alias_of_recall_at_k": True,
        **_eval_protocol(),
        "hits": recall_metrics["hits"],
        "citation_page_hit_rate": (page_hit / page_total) if page_total else None,
        "page_eval_count": page_total,
        "citation_page_hits": page_hit,
        "strict_citation_page_hit_rate": (strict_hit / strict_total) if strict_total else None,
        "strict_citation_eval_count": strict_total,
        "strict_citation_hits": strict_hit,
        **cfg_from_rows,
        "skip_generation": skip_generation,
        "ragas": ragas_metrics,
        "elapsed_ms": round(elapsed_ms, 2),
    }
    if extra_metrics:
        metrics.update(extra_metrics)
    return metrics


def annotate_row_strict_citation(row: dict[str, Any]) -> dict[str, Any]:
    """Offline: fill hit_page_strict from stored Top-K (filename, page) pairs."""
    row["hit_page_strict"] = strict_citation_hit(
        retrieved_files=row.get("retrieved_files") or [],
        retrieved_pages=row.get("retrieved_pages") or [],
        expected_filename=row.get("expected_filename"),
        expected_page=row.get("expected_page_hint"),
    )
    return row


def _eval_protocol() -> dict[str, Any]:
    """Frozen metric/latency/limitation notes stored on every Phase5 metrics blob."""
    return {
        "eval_protocol": {
            "dataset": "data/eval/questions.json",
            "dataset_size_field": "total",
            "hit_at_k": "alias of recall_at_k (same Top-K filename/doc_id boolean)",
            "recall_at_k": "expected filename substring or expected_doc_id in scored Top-K",
            "citation_page_hit_rate": "loose: expected_page_hint in retrieved_pages (page number only)",
            "strict_citation_page_hit_rate": "strict: some retrieved (filename, page) matches expected filename substring AND expected_page_hint",
            "retrieval_latency": "sum(retrieve_ms); Hybrid candidate-k warmup retrieve is excluded",
            "rerank_latency": "sum(rerank_ms); 0 when use_reranker is false",
            "total_latency": "retrieval_latency + rerank_latency (per-config elapsed_ms)",
            "latency_not_stable": [
                "ollama_query_embedding_warmup",
                "dashscope_rerank_network",
            ],
            "limitations": [
                "n=30; page metrics exclude questions with null expected_page_hint",
                "filename match is case-insensitive substring, not exact path equality",
                "docx chunks may have page=0",
                "Hybrid@k widths are independent retrieve_candidates(k) calls, not prefixes of a larger list",
                "Hit@K is not a separate ranking metric",
            ],
        }
    }


def _ablation_latency_fields(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
) -> dict[str, Any]:
    """Split Hybrid@20 vs rerank latency from per-question timings.

    A elapsed = sum(retrieve_ms)
    B elapsed = sum(retrieve_ms) + sum(rerank_ms)
    """
    retrieve_ms_total = round(sum(float(r.get("retrieve_ms") or 0) for r in rows_a), 2)
    rerank_ms_total = round(sum(float(r.get("rerank_ms") or 0) for r in rows_b), 2)
    latency_hybrid20_ms = retrieve_ms_total
    latency_hybrid20_rerank_ms = round(retrieve_ms_total + rerank_ms_total, 2)
    return {
        "retrieve_ms_total": retrieve_ms_total,
        "rerank_ms_total": rerank_ms_total,
        "latency_hybrid20_ms": latency_hybrid20_ms,
        "latency_hybrid20_rerank_ms": latency_hybrid20_rerank_ms,
        "retrieval_latency_ms": retrieve_ms_total,
        "sample_count": len(rows_a),
        "dataset_size": len(rows_a),
        "citation_page_hit_rate_kind": "loose_page_number_only",
        "strict_citation_page_hit_rate_kind": "filename_and_page_pair",
        **_eval_protocol(),
    }


def refresh_ablation_reports_from_json(
    json_a: str | Path | None = None,
    json_b: str | Path | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Recompute strict citation + latency on existing ablation JSON (no retrieval)."""
    cfg = settings or get_settings()
    root = Path(__file__).resolve().parents[2]
    default_dir = root / "evaluation" / "phase5"
    path_a = Path(json_a or (default_dir / "recall_hybrid20.json"))
    path_b = Path(json_b or (default_dir / "recall_hybrid20_rerank.json"))
    payload_a = json.loads(path_a.read_text(encoding="utf-8"))
    payload_b = json.loads(path_b.read_text(encoding="utf-8"))
    rows_a = [annotate_row_strict_citation(dict(r)) for r in payload_a.get("rows") or []]
    rows_b = [annotate_row_strict_citation(dict(r)) for r in payload_b.get("rows") or []]
    latency = _ablation_latency_fields(rows_a, rows_b)
    extra_base = {
        "skip_generation": True,
        "candidates_identical": (payload_a.get("metrics") or {}).get("candidates_identical", True),
        "ablation": (payload_a.get("metrics") or {}).get("ablation", "hybrid20_rerank"),
        **latency,
    }
    extra_a = {
        **extra_base,
        "rerank_latency_ms": 0.0,
        "total_latency_ms": latency["latency_hybrid20_ms"],
    }
    extra_b = {
        **extra_base,
        "rerank_latency_ms": latency["rerank_ms_total"],
        "total_latency_ms": latency["latency_hybrid20_rerank_ms"],
    }
    metrics_a = _aggregate_rows(
        rows_a,
        elapsed_ms=latency["latency_hybrid20_ms"],
        skip_generation=True,
        extra_metrics=extra_a,
    )
    metrics_b = _aggregate_rows(
        rows_b,
        elapsed_ms=latency["latency_hybrid20_rerank_ms"],
        skip_generation=True,
        extra_metrics=extra_b,
    )
    out_a = _write_reports(
        metrics_a,
        rows_a,
        cfg,
        path_a.with_suffix(".md"),
        path_a,
    )
    out_b = _write_reports(
        metrics_b,
        rows_b,
        cfg,
        path_b.with_suffix(".md"),
        path_b,
    )
    return {"A": out_a, "B": out_b}


def refresh_candidate_k_reports_from_json(
    out_dir: str | Path | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Rewrite candidate_k JSON/MD from stored rows (no retrieval/rerank)."""
    cfg = settings or get_settings()
    root = Path(__file__).resolve().parents[2]
    dest = Path(out_dir or (root / "evaluation" / "phase5" / "candidate_k"))
    payloads: dict[str, dict[str, Any]] = {}
    names = ("hybrid10", "hybrid20", "hybrid30", "hybrid20_rerank")
    for name in names:
        path = dest / f"{name}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = [annotate_row_strict_citation(dict(r)) for r in data.get("rows") or []]
        latency = _candidate_k_latency(rows)
        extra = {
            "skip_generation": True,
            "ablation": (data.get("metrics") or {}).get("ablation", "candidate_k"),
            "config_name": name,
            **latency,
        }
        if name == "hybrid20_rerank":
            extra["hybrid20_candidates_shared"] = (data.get("metrics") or {}).get(
                "hybrid20_candidates_shared", True
            )
        metrics = _aggregate_rows(
            rows,
            elapsed_ms=latency["total_latency_ms"],
            skip_generation=True,
            extra_metrics=extra,
        )
        payloads[name] = _write_reports(metrics, rows, cfg, dest / f"{name}.md", path)
    summary = write_candidate_k_summary(
        payloads,
        dest / "summary.md",
        dest / "summary.json",
    )
    return {"payloads": payloads, "summary": summary}


def _fmt_rate(rate: Any, hits: Any, total: Any) -> str:
    if rate is None:
        return "N/A"
    try:
        return f"{float(rate):.2%} ({hits}/{total})"
    except (TypeError, ValueError):
        return str(rate)


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

    - Recall@K：期望 filename / doc_id 出现在检索 Top-K（对 retrieved[:top_k] 计分）
    - RAGAS-style：faithfulness / answer_relevancy / context_precision（+ must_include）
    """
    cfg = settings or get_settings()
    cfg = cfg.model_copy(update={"use_conversation_memory": False})
    qa = qa_service or QAService(cfg)

    questions = load_questions(questions_path)
    rows: list[dict[str, Any]] = []
    ragas_rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    retrieval_mode = resolve_retrieval_mode(cfg)
    top_k = cfg.top_k

    for idx, item in enumerate(questions, start=1):
        question = str(item.get("question") or "").strip()
        if not question:
            continue

        t0 = time.perf_counter()
        retrieved, meta = qa.retrieve(question, use_reranker=cfg.use_reranker)
        retrieve_ms = (time.perf_counter() - t0) * 1000

        mode = str(meta.get("retrieval_mode") or retrieval_mode)
        recall_k = int(meta.get("recall_k") if meta.get("recall_k") is not None else top_k)
        candidate_count = int(
            meta.get("candidate_count")
            if meta.get("candidate_count") is not None
            else len(retrieved)
        )
        use_reranker = bool(meta.get("use_reranker"))
        scored = _score_docs(retrieved, item, top_k=top_k)
        doc_ok = bool(scored["hit_doc"])
        cfg_fields = _config_fields(
            retrieval_mode=mode,
            recall_k=recall_k,
            candidate_count=candidate_count,
            top_k=top_k,
            use_reranker=use_reranker,
        )

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
                contexts=scored["contexts"],
                ground_truth=str(item.get("ground_truth")) if item.get("ground_truth") else None,
                must_include=item.get("must_include") or [],
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
            "expected_doc_id": item.get("expected_doc_id"),
            "expected_filename": item.get("expected_filename"),
            "expected_page_hint": item.get("expected_page_hint"),
            "ground_truth": item.get("ground_truth"),
            "hit_doc": scored["hit_doc"],
            "hit_page": scored["hit_page"],
            "hit_page_strict": scored["hit_page_strict"],
            "retrieved_doc_ids": scored["retrieved_doc_ids"],
            "retrieved_files": scored["retrieved_files"],
            "retrieved_pages": scored["retrieved_pages"],
            "retrieve_ms": round(retrieve_ms, 2),
            "generate_ms": round(gen_ms, 2),
            "final_answer": answer_text[:500],
            "mode": meta.get("mode"),
            "ragas": ragas,
            **cfg_fields,
        }
        rows.append(row)
        logger.info(
            "eval_item_done",
            idx=idx,
            hit_doc=doc_ok,
            retrieval_mode=mode,
            recall_k=recall_k,
            candidate_count=candidate_count,
            top_k=top_k,
            use_reranker=use_reranker,
            retrieve_ms=round(retrieve_ms, 2),
            generate_ms=round(gen_ms, 2),
        )

    metrics = _aggregate_rows(
        rows,
        elapsed_ms=(time.perf_counter() - started) * 1000,
        skip_generation=skip_generation,
        ragas_rows=ragas_rows,
    )
    return _write_reports(metrics, rows, cfg, report_path, json_report_path)


def run_rerank_ablation(
    questions_path: str | Path,
    qa_service: QAService | None = None,
    settings: Settings | None = None,
    *,
    report_a: str | Path | None = None,
    json_a: str | Path | None = None,
    report_b: str | Path | None = None,
    json_b: str | Path | None = None,
) -> dict[str, Any]:
    """
    Fair reranker ablation on one Hybrid@20 candidate list per question.

    A: RRF order [:top_k], use_reranker=false
    B: rerank(candidates) → top_k, use_reranker=true
    """
    cfg = settings or get_settings()
    cfg = cfg.model_copy(
        update={
            "use_conversation_memory": False,
            "retrieval_mode": "hybrid",
            "use_bm25": True,
        }
    )
    qa = qa_service or QAService(cfg)
    qa.settings = cfg

    questions = load_questions(questions_path)
    rows_a: list[dict[str, Any]] = []
    rows_b: list[dict[str, Any]] = []
    recall_k = cfg.recall_top_n
    top_k = cfg.top_k
    candidates_identical = True

    for idx, item in enumerate(questions, start=1):
        question = str(item.get("question") or "").strip()
        if not question:
            continue

        t0 = time.perf_counter()
        candidates = qa.retrieve_candidates(question, k=recall_k)
        retrieve_ms = (time.perf_counter() - t0) * 1000
        candidate_count = len(candidates)
        candidate_ids = _chunk_ids(candidates)

        docs_a = _slice_top_k(candidates, top_k)
        t1 = time.perf_counter()
        docs_b = qa.reranker.rerank(question, candidates, top_n=top_k)
        rerank_ms = (time.perf_counter() - t1) * 1000

        scored_a = _score_docs(docs_a, item, top_k=top_k)
        scored_b = _score_docs(docs_b, item, top_k=top_k)
        skipped_ragas = {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": 1.0 if scored_a["hit_doc"] else 0.0,
            "must_include_pass": None,
        }
        skipped_b = {
            **skipped_ragas,
            "context_precision": 1.0 if scored_b["hit_doc"] else 0.0,
        }

        base = {
            "id": item.get("id") or f"q{idx}",
            "question": question,
            "expected_doc_id": item.get("expected_doc_id"),
            "expected_filename": item.get("expected_filename"),
            "expected_page_hint": item.get("expected_page_hint"),
            "ground_truth": item.get("ground_truth"),
            "candidate_chunk_ids": candidate_ids,
            "retrieve_ms": round(retrieve_ms, 2),
            "generate_ms": 0.0,
            "final_answer": "",
        }
        row_a = {
            **base,
            **scored_a,
            "ragas": skipped_ragas,
            "mode": "hybrid",
            "rerank_ms": 0.0,
            **_config_fields(
                retrieval_mode="hybrid",
                recall_k=recall_k,
                candidate_count=candidate_count,
                top_k=top_k,
                use_reranker=False,
            ),
        }
        row_b = {
            **base,
            **scored_b,
            "ragas": skipped_b,
            "mode": "hybrid_rerank",
            "rerank_ms": round(rerank_ms, 2),
            **_config_fields(
                retrieval_mode="hybrid",
                recall_k=recall_k,
                candidate_count=candidate_count,
                top_k=top_k,
                use_reranker=True,
            ),
        }
        row_a.pop("contexts", None)
        row_b.pop("contexts", None)
        rows_a.append(row_a)
        rows_b.append(row_b)
        if row_a["candidate_chunk_ids"] != row_b["candidate_chunk_ids"]:
            candidates_identical = False
        logger.info(
            "eval_ablation_item_done",
            idx=idx,
            hit_doc_a=row_a["hit_doc"],
            hit_doc_b=row_b["hit_doc"],
            recall_k=recall_k,
            candidate_count=candidate_count,
            top_k=top_k,
            retrieve_ms=round(retrieve_ms, 2),
            rerank_ms=round(rerank_ms, 2),
        )

    latency = _ablation_latency_fields(rows_a, rows_b)
    extra_base = {
        "skip_generation": True,
        "candidates_identical": candidates_identical,
        "ablation": "hybrid20_rerank",
        **latency,
    }
    elapsed_a = latency["latency_hybrid20_ms"]
    elapsed_b = latency["latency_hybrid20_rerank_ms"]
    metrics_a = _aggregate_rows(
        rows_a,
        elapsed_ms=elapsed_a,
        skip_generation=True,
        extra_metrics={**extra_base, "rerank_latency_ms": 0.0, "total_latency_ms": elapsed_a},
    )
    metrics_b = _aggregate_rows(
        rows_b,
        elapsed_ms=elapsed_b,
        skip_generation=True,
        extra_metrics={
            **extra_base,
            "rerank_latency_ms": latency["rerank_ms_total"],
            "total_latency_ms": elapsed_b,
        },
    )

    root = Path(__file__).resolve().parents[2]
    default_dir = root / "evaluation" / "phase5"
    payload_a = _write_reports(
        metrics_a,
        rows_a,
        cfg,
        report_a or (default_dir / "recall_hybrid20.md"),
        json_a or (default_dir / "recall_hybrid20.json"),
    )
    payload_b = _write_reports(
        metrics_b,
        rows_b,
        cfg,
        report_b or (default_dir / "recall_hybrid20_rerank.md"),
        json_b or (default_dir / "recall_hybrid20_rerank.json"),
    )
    return {
        "candidates_identical": candidates_identical,
        "A": payload_a,
        "B": payload_b,
    }


def _sum_row_ms(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(float(r.get(key) or 0) for r in rows), 2)


def _candidate_k_latency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_latency_ms = _sum_row_ms(rows, "retrieve_ms")
    rerank_latency_ms = _sum_row_ms(rows, "rerank_ms")
    total_latency_ms = round(retrieval_latency_ms + rerank_latency_ms, 2)
    n = len(rows)
    return {
        "retrieval_latency_ms": retrieval_latency_ms,
        "rerank_latency_ms": rerank_latency_ms,
        "total_latency_ms": total_latency_ms,
        "sample_count": n,
        "n_questions": n,
        "citation_page_hit_rate_kind": "loose_page_number_only",
        "strict_citation_page_hit_rate_kind": "filename_and_page_pair",
        **_eval_protocol(),
    }


def _score_skip_generation_row(
    *,
    item: dict[str, Any],
    idx: int,
    question: str,
    candidates: list[Document],
    ranked: list[Document],
    retrieve_ms: float,
    rerank_ms: float,
    recall_k: int,
    top_k: int,
    use_reranker: bool,
    mode: str,
) -> dict[str, Any]:
    scored = _score_docs(ranked, item, top_k=top_k)
    row = {
        "id": item.get("id") or f"q{idx}",
        "question": question,
        "expected_doc_id": item.get("expected_doc_id"),
        "expected_filename": item.get("expected_filename"),
        "expected_page_hint": item.get("expected_page_hint"),
        "ground_truth": item.get("ground_truth"),
        "candidate_chunk_ids": _chunk_ids(candidates),
        "retrieve_ms": round(retrieve_ms, 2),
        "rerank_ms": round(rerank_ms, 2),
        "generate_ms": 0.0,
        "final_answer": "",
        **scored,
        "ragas": {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": 1.0 if scored["hit_doc"] else 0.0,
            "must_include_pass": None,
        },
        "mode": mode,
        **_config_fields(
            retrieval_mode="hybrid",
            recall_k=recall_k,
            candidate_count=len(candidates),
            top_k=top_k,
            use_reranker=use_reranker,
        ),
    }
    row.pop("contexts", None)
    return row


def recommend_candidate_k_config(configs: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick serving config: best Recall@5, then smaller recall_k."""
    if not configs:
        raise ValueError("configs must be non-empty")
    best_recall = max(float(c.get("recall_at_k") or 0) for c in configs)
    quality = [c for c in configs if float(c.get("recall_at_k") or 0) == best_recall]
    quality_pick = min(
        quality,
        key=lambda c: (int(c.get("recall_k") or 10**9), float(c.get("total_latency_ms") or 0)),
    )
    no_rerank = [c for c in configs if not c.get("use_reranker")]
    pool = no_rerank or configs
    best_nr = max(float(c.get("recall_at_k") or 0) for c in pool)
    nr_tied = [c for c in pool if float(c.get("recall_at_k") or 0) == best_nr]
    latency_pick = min(
        nr_tied,
        key=lambda c: (int(c.get("recall_k") or 10**9), float(c.get("total_latency_ms") or 0)),
    )
    return {
        "adopted": quality_pick.get("name"),
        "quality_first": quality_pick.get("name"),
        "latency_first": latency_pick.get("name"),
        "best_recall_at_k": best_recall,
    }


def write_candidate_k_summary(
    payloads: dict[str, dict[str, Any]],
    summary_md: str | Path,
    summary_json: str | Path | None = None,
) -> dict[str, Any]:
    """Write a cross-config comparison; does not rewrite per-config JSON."""
    order = ["hybrid10", "hybrid20", "hybrid30", "hybrid20_rerank"]
    labels = {
        "hybrid10": "Hybrid@10",
        "hybrid20": "Hybrid@20",
        "hybrid30": "Hybrid@30",
        "hybrid20_rerank": "Hybrid@20 + Reranker(top_k=5)",
    }
    configs: list[dict[str, Any]] = []
    for key in order:
        if key not in payloads:
            continue
        metrics = payloads[key]["metrics"]
        configs.append(
            {
                "name": labels[key],
                "key": key,
                "use_reranker": bool(metrics.get("use_reranker")),
                "recall_k": metrics.get("recall_k"),
                "top_k": metrics.get("top_k"),
                "sample_count": metrics.get("sample_count") or metrics.get("total"),
                "recall_at_k": metrics.get("recall_at_k"),
                "hit_at_k": metrics.get("hit_at_k"),
                "hits": metrics.get("hits"),
                "total": metrics.get("total"),
                "citation_page_hit_rate": metrics.get("citation_page_hit_rate"),
                "citation_page_hits": metrics.get("citation_page_hits"),
                "page_eval_count": metrics.get("page_eval_count"),
                "strict_citation_page_hit_rate": metrics.get("strict_citation_page_hit_rate"),
                "strict_citation_hits": metrics.get("strict_citation_hits"),
                "strict_citation_eval_count": metrics.get("strict_citation_eval_count"),
                "retrieval_latency_ms": metrics.get("retrieval_latency_ms"),
                "rerank_latency_ms": metrics.get("rerank_latency_ms"),
                "total_latency_ms": metrics.get("total_latency_ms") or metrics.get("elapsed_ms"),
            }
        )
    rec = recommend_candidate_k_config(configs)
    adopted = next(c for c in configs if c["name"] == rec["adopted"])
    latency_first = next(c for c in configs if c["name"] == rec["latency_first"])

    def _pct(rate: Any, hits: Any, total: Any) -> str:
        return _fmt_rate(rate, hits, total)

    lines = [
        "# Phase5 candidate/top-k 消融对比",
        "",
        "本轮只改变 Hybrid 召回宽度 `recall_k` ∈ {10, 20, 30}，以及是否在 Hybrid@20 候选上调用已有 reranker。",
        "题集、ground truth、embedding、BM25、RRF 公式、reranker 实现均未改动；不生成答案。",
        "Hybrid@k 各自调用 `retrieve_candidates(k)`（Dense@k + BM25@k + RRF 截断到 k），不是从更大候选集切片。",
        "Hybrid@20 与 Hybrid@20+Reranker 共享同一组 k=20 候选。计分一律 Top-5。",
        "新结果写在 `evaluation/phase5/candidate_k/`，不覆盖已有 `recall_hybrid20*.json`。",
        "",
        "## 横向对比",
        "",
        "| 配置 | n | Recall@5 | loose page hit | strict citation hit | retrieval ms | rerank ms | total ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for c in configs:
        rec_s = _pct(c["recall_at_k"], c["hits"], c["total"])
        loose = _pct(c["citation_page_hit_rate"], c["citation_page_hits"], c["page_eval_count"])
        strict = _pct(
            c["strict_citation_page_hit_rate"],
            c["strict_citation_hits"],
            c["strict_citation_eval_count"],
        )
        lines.append(
            f"| {c['name']} | {c['sample_count']} | {rec_s} | {loose} | {strict} | "
            f"{c['retrieval_latency_ms']} | {c['rerank_latency_ms']} | {c['total_latency_ms']} |"
        )

    lines.extend(
        [
            "",
            "## 推荐配置",
            "",
            f"- **本轮建议采用：{rec['adopted']}**",
            f"- 效果优先（最高 Recall@5，并列取更小 recall_k）：`{rec['quality_first']}`",
            f"- 延迟优先（无 rerank 的最高 Recall@5，并列取更小 recall_k）：`{rec['latency_first']}`",
            "",
            f"{rec['adopted']} 的 Recall@5 为 **{_pct(adopted['recall_at_k'], adopted['hits'], adopted['total'])}**，"
            f"总延迟 **{adopted['total_latency_ms']} ms**；"
            f"相对延迟优先配置 `{latency_first['name']}` "
            f"（Recall@5 {_pct(latency_first['recall_at_k'], latency_first['hits'], latency_first['total'])}，"
            f"{latency_first['total_latency_ms']} ms），"
            f"效果按 Recall 命中数差 {int(adopted['hits'] or 0) - int(latency_first['hits'] or 0)} 题，"
            f"延迟差 {round(float(adopted['total_latency_ms'] or 0) - float(latency_first['total_latency_ms'] or 0), 2)} ms。",
            "",
            "无 rerank 的 Hybrid@10/20/30 若 Recall@5 相同，则延迟优先取更小的 `recall_k`："
            "本语料上检索延迟主要由 query embedding 决定，k 之间几百毫秒的差异不足以当作吞吐结论。",
            "",
            "## 公平性说明",
            "",
            "- 30 条 evaluation queries 与 ground truth 未改。",
            "- 各 Hybrid@k 是独立宽召回，不是同一 30 候选的前缀；因此 k 之间的 Recall 差反映的是「生产 Hybrid@k 的 Top-5」，不能直接解读为「多召回的那 10 条单独贡献」。",
            "- 延迟：每个 `recall_k` 对全部题目整段测完再测下一段，避免同一题内 10→20→30 把 encoder 预热算进较小的 k。Hybrid@20+Rerank 的 retrieval 延迟复用 Hybrid@20 段，不再检索一次。",
            "- Hybrid@20 vs Hybrid@20+Rerank 共享候选，与既有 A/B 设计一致。",
            "- Hit@K JSON 字段 `hit_at_k` 是 Recall@K 的别名，本表不重复展示。",
            "- `citation_page_hit_rate` 仍是 loose（只看页码）；`strict_citation_page_hit_rate` 要求 `(filename, page)` 同时匹配。",
            "- 耗时 = `sum(retrieve_ms)`，rerank 配置再加 `sum(rerank_ms)`；不含生成。循环前有一次 warmup retrieve，不计入指标。",
            "- 本目录结果与 `evaluation/phase5/recall_hybrid20*.json` 不是同一次检索，数值可能因 encoder 预热而有毫秒～秒级差异，Recall 在确定性索引上应一致。",
            "",
        ]
    )
    md_path = Path(summary_md)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines), encoding="utf-8")
    blob = {"configs": configs, "recommendation": rec, "summary_path": str(md_path)}
    if summary_json is not None:
        jpath = Path(summary_json)
        jpath.parent.mkdir(parents=True, exist_ok=True)
        jpath.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
        blob["json_summary_path"] = str(jpath)
    return blob


def run_candidate_k_ablation(
    questions_path: str | Path,
    qa_service: QAService | None = None,
    settings: Settings | None = None,
    *,
    out_dir: str | Path | None = None,
    recall_ks: tuple[int, ...] = (10, 20, 30),
    top_k: int | None = None,
    include_rerank_on_20: bool = True,
) -> dict[str, Any]:
    """Hybrid@k candidate-width ablation. Does not overwrite existing Hybrid@20 A/B JSON."""
    cfg = settings or get_settings()
    cfg = cfg.model_copy(
        update={
            "use_conversation_memory": False,
            "retrieval_mode": "hybrid",
            "use_bm25": True,
        }
    )
    qa = qa_service or QAService(cfg)
    qa.settings = cfg
    eval_top_k = int(top_k if top_k is not None else cfg.top_k)

    questions = load_questions(questions_path)
    items: list[tuple[int, dict[str, Any], str]] = []
    for idx, item in enumerate(questions, start=1):
        question = str(item.get("question") or "").strip()
        if question:
            items.append((idx, item, question))

    rows_by_k: dict[int, list[dict[str, Any]]] = {int(k): [] for k in recall_ks}
    rows_rerank: list[dict[str, Any]] = []
    hybrid20_rerank_shared = True
    stored_20: dict[str, tuple[list[Document], float]] = {}

    try:
        qa.retrieve_candidates("warmup", k=min(recall_ks) if recall_ks else 1)
    except Exception:
        logger.warning("candidate_k_warmup_failed")

    for recall_k in recall_ks:
        k = int(recall_k)
        for idx, item, question in items:
            t0 = time.perf_counter()
            candidates = qa.retrieve_candidates(question, k=k)
            retrieve_ms = (time.perf_counter() - t0) * 1000
            row = _score_skip_generation_row(
                item=item,
                idx=idx,
                question=question,
                candidates=candidates,
                ranked=_slice_top_k(candidates, eval_top_k),
                retrieve_ms=retrieve_ms,
                rerank_ms=0.0,
                recall_k=k,
                top_k=eval_top_k,
                use_reranker=False,
                mode=f"hybrid{k}",
            )
            rows_by_k[k].append(row)
            if include_rerank_on_20 and k == 20:
                stored_20[str(row["id"])] = (candidates, retrieve_ms)
        logger.info("eval_candidate_k_config_done", recall_k=k, n=len(rows_by_k[k]))

    if include_rerank_on_20 and 20 in rows_by_k and stored_20:
        for idx, item, question in items:
            qid = str(item.get("id") or f"q{idx}")
            c20, retrieve_ms = stored_20[qid]
            t1 = time.perf_counter()
            ranked_b = qa.reranker.rerank(question, c20, top_n=eval_top_k)
            rerank_ms = (time.perf_counter() - t1) * 1000
            row_b = _score_skip_generation_row(
                item=item,
                idx=idx,
                question=question,
                candidates=c20,
                ranked=ranked_b,
                retrieve_ms=retrieve_ms,
                rerank_ms=rerank_ms,
                recall_k=20,
                top_k=eval_top_k,
                use_reranker=True,
                mode="hybrid20_rerank",
            )
            rows_rerank.append(row_b)
            hybrid20_row = next(r for r in rows_by_k[20] if str(r["id"]) == qid)
            if row_b["candidate_chunk_ids"] != hybrid20_row["candidate_chunk_ids"]:
                hybrid20_rerank_shared = False
        logger.info("eval_candidate_k_rerank_done", n=len(rows_rerank))

    root = Path(__file__).resolve().parents[2]
    dest = Path(out_dir or (root / "evaluation" / "phase5" / "candidate_k"))
    dest.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, dict[str, Any]] = {}
    key_by_k = {10: "hybrid10", 20: "hybrid20", 30: "hybrid30"}
    for k, rows in rows_by_k.items():
        latency = _candidate_k_latency(rows)
        extra = {
            "skip_generation": True,
            "ablation": "candidate_k",
            "config_name": key_by_k.get(k, f"hybrid{k}"),
            **latency,
        }
        metrics = _aggregate_rows(
            rows,
            elapsed_ms=latency["total_latency_ms"],
            skip_generation=True,
            extra_metrics=extra,
        )
        name = extra["config_name"]
        payloads[name] = _write_reports(
            metrics,
            rows,
            cfg,
            dest / f"{name}.md",
            dest / f"{name}.json",
        )

    if include_rerank_on_20 and rows_rerank:
        latency = _candidate_k_latency(rows_rerank)
        extra = {
            "skip_generation": True,
            "ablation": "candidate_k",
            "config_name": "hybrid20_rerank",
            "hybrid20_candidates_shared": hybrid20_rerank_shared,
            **latency,
        }
        metrics = _aggregate_rows(
            rows_rerank,
            elapsed_ms=latency["total_latency_ms"],
            skip_generation=True,
            extra_metrics=extra,
        )
        payloads["hybrid20_rerank"] = _write_reports(
            metrics,
            rows_rerank,
            cfg,
            dest / "hybrid20_rerank.md",
            dest / "hybrid20_rerank.json",
        )

    summary = write_candidate_k_summary(
        payloads,
        dest / "summary.md",
        dest / "summary.json",
    )
    return {
        "out_dir": str(dest),
        "hybrid20_candidates_shared": hybrid20_rerank_shared,
        "payloads": payloads,
        "summary": summary,
    }


def _render_markdown(metrics: dict[str, Any], rows: list[dict[str, Any]], cfg: Settings) -> str:
    ragas = metrics.get("ragas") or {}
    top_k = metrics.get("top_k", cfg.top_k)
    loose_label = _fmt_rate(
        metrics.get("citation_page_hit_rate"),
        metrics.get("citation_page_hits"),
        metrics.get("page_eval_count"),
    )
    strict_label = _fmt_rate(
        metrics.get("strict_citation_page_hit_rate"),
        metrics.get("strict_citation_hits"),
        metrics.get("strict_citation_eval_count"),
    )
    lines = [
        "# Enterprise RAG — Phase5 评测报告",
        "",
        "## 汇总",
        "",
        f"- 题目总数: **{metrics.get('total')}**",
        f"- Recall@{top_k}: **{float(metrics.get('recall_at_k') or 0):.2%}** "
        f"({metrics.get('hits')}/{metrics.get('total')})",
        f"- citation_page_hit_rate（loose page hit，仅页码）: **{loose_label}**",
        f"- strict_citation_page_hit_rate（strict citation hit，filename+page）: **{strict_label}**",
        f"- retrieval_mode: `{metrics.get('retrieval_mode')}`",
        f"- recall_k: `{metrics.get('recall_k')}`",
        f"- candidate_count: `{metrics.get('candidate_count')}`",
        f"- top_k: `{metrics.get('top_k')}`",
        f"- use_reranker: `{metrics.get('use_reranker')}`",
        f"- use_bm25: `{metrics.get('use_bm25')}`",
        f"- elapsed_ms: `{metrics.get('elapsed_ms')}`",
    ]
    retrieval_ms = metrics.get("retrieval_latency_ms")
    if retrieval_ms is None:
        retrieval_ms = metrics.get("retrieve_ms_total")
    rerank_ms = metrics.get("rerank_latency_ms")
    if rerank_ms is None:
        rerank_ms = metrics.get("rerank_ms_total")
    total_ms = metrics.get("total_latency_ms")
    if total_ms is None:
        total_ms = metrics.get("elapsed_ms")
    if retrieval_ms is not None:
        lines.extend(
            [
                f"- retrieval latency (`retrieval_latency_ms`): `{retrieval_ms}`",
                f"- rerank latency (`rerank_latency_ms`): `{rerank_ms}`",
                f"- total latency (`total_latency_ms` / this-report `elapsed_ms`): `{total_ms}`",
                f"- sample_count / dataset size: `{metrics.get('sample_count') or metrics.get('total')}`",
            ]
        )
    if metrics.get("retrieve_ms_total") is not None:
        lines.extend(
            [
                f"- Hybrid@20 retrieval total time (`retrieve_ms_total`): `{metrics.get('retrieve_ms_total')}`",
                f"- Reranker total time (`rerank_ms_total`): `{metrics.get('rerank_ms_total')}`",
                f"- Hybrid@20 total latency (`latency_hybrid20_ms`): `{metrics.get('latency_hybrid20_ms')}`",
                f"- Hybrid@20 + Reranker total latency (`latency_hybrid20_rerank_ms`): "
                f"`{metrics.get('latency_hybrid20_rerank_ms')}`",
            ]
        )
    lines.extend(
        [
            "",
            "### 配置 / 指标定义 / 延迟口径 / 限制",
            "",
            f"- dataset: `data/eval/questions.json`（size=`{metrics.get('total')}`）",
            f"- retrieval: mode=`{metrics.get('retrieval_mode')}` · recall_k=`{metrics.get('recall_k')}` · "
            f"top_k=`{metrics.get('top_k')}` · use_bm25=`{metrics.get('use_bm25')}`",
            f"- reranker: use_reranker=`{metrics.get('use_reranker')}` · "
            f"backend=`{getattr(cfg, 'reranker_backend', None)}` · "
            f"dashscope_model=`{getattr(cfg, 'dashscope_rerank_model', None)}` "
            "（backend/model 取报告生成时 Settings，历史 JSON 行内只保证 `use_reranker`）",
            f"- Recall@{top_k}: 期望 filename 子串或 expected_doc_id 出现在评分 Top-K。",
            "- `hit_at_k` 是 `recall_at_k` 的别名，不单独展示。",
            "- citation_page_hit_rate：loose page hit，只要求页码出现在 Top-K。",
            "- strict_citation_page_hit_rate：retrieved `(filename, page)` 同时匹配期望 filename 与 expected_page_hint。",
            "- retrieval latency = `sum(retrieve_ms)`；rerank latency = `sum(rerank_ms)`；"
            "total = 二者之和（本报告 `elapsed_ms`）。",
            "- 延迟含 Ollama embedding 与 DashScope rerank 网络波动；candidate-k 有一次不计入的 warmup retrieve；"
            "A/B 首题含冷启动。不同次运行的 ms 不可直接当吞吐基准。",
            "- 限制：n=30；无 page hint 的题不进 citation 分母；docx 可能 page=0；"
            "filename 为大小写不敏感子串；Hybrid@k 宽度是独立召回不是同一列表前缀。",
            "",
            "### RAGAS-style 指标",
            "",
        ]
    )
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
        lines.append(f"- expected_page_hint: `{row.get('expected_page_hint')}`")
        lines.append(f"- hit_doc (Recall): **{row.get('hit_doc')}**")
        lines.append(f"- hit_page (loose page hit): {row.get('hit_page')}")
        lines.append(f"- hit_page_strict (strict citation hit): {row.get('hit_page_strict')}")
        lines.append(f"- retrieval_mode: `{row.get('retrieval_mode')}`")
        lines.append(f"- recall_k: `{row.get('recall_k')}`")
        lines.append(f"- candidate_count: `{row.get('candidate_count')}`")
        lines.append(f"- top_k: `{row.get('top_k')}`")
        lines.append(f"- use_reranker: `{row.get('use_reranker')}`")
        lines.append(f"- use_bm25: `{row.get('use_bm25')}`")
        lines.append(f"- retrieve_ms: `{row.get('retrieve_ms')}`")
        if row.get("rerank_ms") is not None:
            lines.append(f"- rerank_ms: `{row.get('rerank_ms')}`")
        lines.append(f"- retrieved_files: {row.get('retrieved_files')}")
        lines.append(f"- retrieved_pages: {row.get('retrieved_pages')}")
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
