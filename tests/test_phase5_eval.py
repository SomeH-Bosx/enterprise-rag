"""Phase5 eval unit tests (no live Ollama required)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.eval.ragas_lite import (
    aggregate_ragas_style,
    answer_relevancy_score,
    faithfulness_score,
    must_include_pass,
    score_row,
)
from src.eval.recall import aggregate_recall, recall_hit, strict_citation_hit


def test_recall_hit_by_filename():
    assert recall_hit(
        retrieved_files=["acme_employee_handbook.pdf", "other.pdf"],
        retrieved_doc_ids=["a", "b"],
        expected_filename="acme_employee_handbook.pdf",
    )
    assert not recall_hit(
        retrieved_files=["beta_product_spec.pdf"],
        retrieved_doc_ids=["x"],
        expected_filename="acme_employee_handbook.pdf",
    )


def test_aggregate_recall():
    m = aggregate_recall([True, False, True, True])
    assert m["total"] == 4
    assert m["hits"] == 3
    assert m["recall_at_k"] == 0.75


def test_faithfulness_and_relevancy():
    ctx = ["Annual leave is 15 days for full-time employees."]
    ans = "Employees get 15 days annual leave."
    faith = faithfulness_score(ans, ctx)
    relev = answer_relevancy_score(ans, "How many annual leave days?", "15 days")
    assert faith > 0.3
    assert relev > 0.2
    assert must_include_pass(ans, ["15"]) is True
    assert must_include_pass(ans, ["99"]) is False


def test_score_row_and_aggregate():
    row = score_row(
        answer="p95 under 200 milliseconds",
        question="What is the p95 latency SLO?",
        contexts=["Latency SLO: p95 query latency under 200 milliseconds."],
        ground_truth="under 200 milliseconds",
        must_include=["200"],
        context_hit=True,
    )
    assert row["context_precision"] == 1.0
    assert row["must_include_pass"] is True
    agg = aggregate_ragas_style([row, row])
    assert agg["n"] == 2
    assert agg["backend"] == "ragas_lite"
    assert agg["context_precision"] == 1.0


def test_run_eval_records_actual_config_and_slices_top_k(tmp_path: Path):
    from langchain_core.documents import Document

    from src.config.settings import Settings
    from src.eval.runner import run_eval
    from src.services.qa_service import QAService

    questions = [
        {
            "id": "q1",
            "question": "How many leave days?",
            "expected_filename": "handbook.pdf",
            "expected_page_hint": 1,
            "ground_truth": "15",
        }
    ]
    qpath = tmp_path / "questions.json"
    qpath.write_text(json.dumps(questions), encoding="utf-8")

    extra = Document(
        page_content="noise",
        metadata={"chunk_id": "c2", "doc_id": "d2", "filename": "other.pdf", "page": 9},
    )
    gold = Document(
        page_content="15 days",
        metadata={"chunk_id": "c1", "doc_id": "d1", "filename": "handbook.pdf", "page": 1},
    )
    settings = Settings(
        VECTOR_DB_PATH=str(tmp_path / "chroma"),
        BM25_STORE_PATH=str(tmp_path / "bm25.json"),
        DOC_REGISTRY_PATH=str(tmp_path / "registry.json"),
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        UPLOAD_CACHE_DIR=str(tmp_path / "uploads"),
        USE_CONVERSATION_MEMORY=False,
        USE_RERANKER=False,
        USE_BM25=True,
        RETRIEVAL_MODE="dense",
        TOP_K=1,
        RECALL_TOP_N=20,
    )
    qa = QAService(settings)
    qa.retrieve = MagicMock(  # type: ignore[method-assign]
        return_value=(
            [extra, gold],
            {
                "mode": "dense",
                "use_reranker": False,
                "retrieval_mode": "dense",
                "recall_k": 1,
                "candidate_count": 2,
                "top_n": 1,
            },
        )
    )
    payload = run_eval(
        qpath,
        tmp_path / "r.md",
        qa_service=qa,
        settings=settings,
        skip_generation=True,
        json_report_path=tmp_path / "r.json",
    )
    metrics = payload["metrics"]
    assert "recall_top_n" not in metrics
    assert metrics["retrieval_mode"] == "dense"
    assert metrics["recall_k"] == 1
    assert metrics["top_k"] == 1
    assert metrics["use_reranker"] is False
    assert metrics["use_bm25"] is False
    assert payload["rows"][0]["hit_doc"] is False
    assert payload["rows"][0]["retrieved_files"] == ["other.pdf"]


def test_rerank_ablation_shares_candidates(tmp_path: Path):
    from langchain_core.documents import Document

    from src.config.settings import Settings
    from src.eval.runner import run_rerank_ablation
    from src.services.qa_service import QAService

    questions = [
        {
            "id": "q1",
            "question": "How many leave days?",
            "expected_filename": "handbook.pdf",
            "expected_page_hint": 2,
            "ground_truth": "15",
        }
    ]
    qpath = tmp_path / "questions.json"
    qpath.write_text(json.dumps(questions), encoding="utf-8")
    candidates = [
        Document(
            page_content="noise",
            metadata={"chunk_id": "c1", "doc_id": "d1", "filename": "other.pdf", "page": 9},
        ),
        Document(
            page_content="15 days",
            metadata={"chunk_id": "c2", "doc_id": "d2", "filename": "handbook.pdf", "page": 2},
        ),
    ]
    settings = Settings(
        VECTOR_DB_PATH=str(tmp_path / "chroma"),
        BM25_STORE_PATH=str(tmp_path / "bm25.json"),
        DOC_REGISTRY_PATH=str(tmp_path / "registry.json"),
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        UPLOAD_CACHE_DIR=str(tmp_path / "uploads"),
        USE_CONVERSATION_MEMORY=False,
        USE_RERANKER=False,
        USE_BM25=False,
        RETRIEVAL_MODE="dense",
        TOP_K=1,
        RECALL_TOP_N=2,
    )
    qa = QAService(settings)
    qa.retrieve_candidates = MagicMock(return_value=candidates)  # type: ignore[method-assign]
    qa.reranker.rerank = MagicMock(return_value=[candidates[1]])  # type: ignore[method-assign]

    result = run_rerank_ablation(
        qpath,
        qa_service=qa,
        settings=settings,
        report_a=tmp_path / "a.md",
        json_a=tmp_path / "a.json",
        report_b=tmp_path / "b.md",
        json_b=tmp_path / "b.json",
    )
    assert result["candidates_identical"] is True
    row_a = result["A"]["rows"][0]
    row_b = result["B"]["rows"][0]
    assert row_a["candidate_chunk_ids"] == row_b["candidate_chunk_ids"] == ["c1", "c2"]
    assert row_a["use_reranker"] is False
    assert row_b["use_reranker"] is True
    assert row_a["use_bm25"] is True
    assert row_b["use_bm25"] is True
    assert row_a["retrieval_mode"] == row_b["retrieval_mode"] == "hybrid"
    assert row_a["recall_k"] == row_b["recall_k"] == 2
    assert row_a["candidate_count"] == row_b["candidate_count"] == 2
    assert row_a["top_k"] == row_b["top_k"] == 1
    assert row_a["hit_doc"] is False
    assert row_b["hit_doc"] is True
    assert result["A"]["metrics"]["use_reranker"] is False
    assert result["B"]["metrics"]["use_reranker"] is True
    assert "recall_top_n" not in result["A"]["metrics"]
    sum_retrieve = round(sum(float(r["retrieve_ms"]) for r in result["A"]["rows"]), 2)
    sum_rerank = round(sum(float(r["rerank_ms"]) for r in result["B"]["rows"]), 2)
    assert result["A"]["metrics"]["elapsed_ms"] == sum_retrieve
    assert result["B"]["metrics"]["elapsed_ms"] == round(sum_retrieve + sum_rerank, 2)
    assert result["A"]["metrics"]["retrieve_ms_total"] == sum_retrieve
    assert result["B"]["metrics"]["rerank_ms_total"] == sum_rerank
    assert result["A"]["metrics"]["latency_hybrid20_ms"] == sum_retrieve
    assert result["B"]["metrics"]["latency_hybrid20_rerank_ms"] == round(sum_retrieve + sum_rerank, 2)
    assert result["A"]["metrics"]["rerank_latency_ms"] == 0.0
    assert result["A"]["metrics"]["total_latency_ms"] == sum_retrieve
    assert result["B"]["metrics"]["rerank_latency_ms"] == sum_rerank
    assert result["B"]["metrics"]["total_latency_ms"] == round(sum_retrieve + sum_rerank, 2)
    qa.retrieve_candidates.assert_called_once()
    qa.reranker.rerank.assert_called_once()


def test_strict_citation_hit_requires_filename_and_page():
    files = ["hotel.docx", "handbook.pdf"]
    pages = [113, 99]
    # Loose page hit would be True (113 is present); strict requires same file.
    assert 113 in pages
    assert (
        strict_citation_hit(
            retrieved_files=files,
            retrieved_pages=pages,
            expected_filename="handbook.pdf",
            expected_page=113,
        )
        is False
    )
    assert (
        strict_citation_hit(
            retrieved_files=files,
            retrieved_pages=pages,
            expected_filename="handbook.pdf",
            expected_page=99,
        )
        is True
    )
    assert (
        strict_citation_hit(
            retrieved_files=files,
            retrieved_pages=pages,
            expected_filename="handbook.pdf",
            expected_page=None,
        )
        is None
    )


def test_run_eval_loose_page_hit_vs_strict_citation(tmp_path: Path):
    from langchain_core.documents import Document

    from src.config.settings import Settings
    from src.eval.runner import run_eval
    from src.services.qa_service import QAService

    questions = [
        {
            "id": "q1",
            "question": "Scholarship page?",
            "expected_filename": "handbook.pdf",
            "expected_page_hint": 113,
        }
    ]
    qpath = tmp_path / "questions.json"
    qpath.write_text(json.dumps(questions), encoding="utf-8")
    wrong_file_same_page = Document(
        page_content="noise",
        metadata={"chunk_id": "c1", "doc_id": "d1", "filename": "hotel.docx", "page": 113},
    )
    right_file_wrong_page = Document(
        page_content="other",
        metadata={"chunk_id": "c2", "doc_id": "d2", "filename": "handbook.pdf", "page": 5},
    )
    settings = Settings(
        VECTOR_DB_PATH=str(tmp_path / "chroma"),
        BM25_STORE_PATH=str(tmp_path / "bm25.json"),
        DOC_REGISTRY_PATH=str(tmp_path / "registry.json"),
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        UPLOAD_CACHE_DIR=str(tmp_path / "uploads"),
        USE_CONVERSATION_MEMORY=False,
        USE_RERANKER=False,
        USE_BM25=False,
        RETRIEVAL_MODE="dense",
        TOP_K=2,
        RECALL_TOP_N=2,
    )
    qa = QAService(settings)
    qa.retrieve = MagicMock(  # type: ignore[method-assign]
        return_value=(
            [wrong_file_same_page, right_file_wrong_page],
            {
                "mode": "dense",
                "use_reranker": False,
                "retrieval_mode": "dense",
                "recall_k": 2,
                "candidate_count": 2,
                "top_n": 2,
            },
        )
    )
    payload = run_eval(
        qpath,
        tmp_path / "r.md",
        qa_service=qa,
        settings=settings,
        skip_generation=True,
        json_report_path=tmp_path / "r.json",
    )
    row = payload["rows"][0]
    assert row["hit_page"] is True
    assert row["hit_page_strict"] is False
    assert payload["metrics"]["citation_page_hit_rate"] == 1.0
    assert payload["metrics"]["strict_citation_page_hit_rate"] == 0.0


def test_refresh_ablation_reports_from_json_offline(tmp_path: Path):
    from src.config.settings import Settings
    from src.eval.runner import refresh_ablation_reports_from_json

    def _payload(*, use_reranker: bool, retrieve_ms: float, rerank_ms: float) -> dict:
        row = {
            "id": "q1",
            "question": "Scholarship?",
            "expected_filename": "handbook.pdf",
            "expected_page_hint": 113,
            "hit_doc": True,
            "hit_page": True,
            "retrieved_files": ["hotel.docx", "handbook.pdf"],
            "retrieved_pages": [113, 5],
            "retrieve_ms": retrieve_ms,
            "rerank_ms": rerank_ms,
            "retrieval_mode": "hybrid",
            "recall_k": 20,
            "candidate_count": 20,
            "top_k": 5,
            "use_reranker": use_reranker,
            "use_bm25": True,
        }
        return {
            "metrics": {
                "elapsed_ms": 99999.0,
                "candidates_identical": True,
                "ablation": "hybrid20_rerank",
            },
            "rows": [row],
        }

    json_a = tmp_path / "recall_hybrid20.json"
    json_b = tmp_path / "recall_hybrid20_rerank.json"
    json_a.write_text(json.dumps(_payload(use_reranker=False, retrieve_ms=10.0, rerank_ms=0.0)), encoding="utf-8")
    json_b.write_text(json.dumps(_payload(use_reranker=True, retrieve_ms=10.0, rerank_ms=4.5)), encoding="utf-8")
    settings = Settings(
        VECTOR_DB_PATH=str(tmp_path / "chroma"),
        BM25_STORE_PATH=str(tmp_path / "bm25.json"),
        DOC_REGISTRY_PATH=str(tmp_path / "registry.json"),
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        UPLOAD_CACHE_DIR=str(tmp_path / "uploads"),
    )
    result = refresh_ablation_reports_from_json(json_a, json_b, settings=settings)
    assert result["A"]["metrics"]["elapsed_ms"] == 10.0
    assert result["B"]["metrics"]["elapsed_ms"] == 14.5
    assert result["A"]["metrics"]["rerank_latency_ms"] == 0.0
    assert result["B"]["metrics"]["rerank_latency_ms"] == 4.5
    assert result["A"]["metrics"]["citation_page_hit_rate"] == 1.0
    assert result["A"]["metrics"]["strict_citation_page_hit_rate"] == 0.0
    assert result["A"]["rows"][0]["hit_page_strict"] is False
    assert result["A"]["metrics"]["latency_hybrid20_ms"] == 10.0
    assert result["B"]["metrics"]["latency_hybrid20_rerank_ms"] == 14.5
    assert json_a.with_suffix(".md").exists()
    assert json_b.with_suffix(".md").exists()


def test_recommend_candidate_k_prefers_best_recall_then_latency():
    from src.eval.runner import recommend_candidate_k_config

    rec = recommend_candidate_k_config(
        [
            {
                "name": "Hybrid@10",
                "use_reranker": False,
                "recall_k": 10,
                "recall_at_k": 0.80,
                "total_latency_ms": 100,
            },
            {
                "name": "Hybrid@20",
                "use_reranker": False,
                "recall_k": 20,
                "recall_at_k": 0.83,
                "total_latency_ms": 160,
            },
            {
                "name": "Hybrid@30",
                "use_reranker": False,
                "recall_k": 30,
                "recall_at_k": 0.83,
                "total_latency_ms": 140,
            },
            {
                "name": "Hybrid@20 + Reranker(top_k=5)",
                "use_reranker": True,
                "recall_k": 20,
                "recall_at_k": 0.87,
                "total_latency_ms": 310,
            },
        ]
    )
    assert rec["quality_first"] == "Hybrid@20 + Reranker(top_k=5)"
    assert rec["adopted"] == "Hybrid@20 + Reranker(top_k=5)"
    assert rec["latency_first"] == "Hybrid@20"
    tied = recommend_candidate_k_config(
        [
            {"name": "Hybrid@10", "use_reranker": False, "recall_k": 10, "recall_at_k": 0.83, "total_latency_ms": 120},
            {"name": "Hybrid@20", "use_reranker": False, "recall_k": 20, "recall_at_k": 0.83, "total_latency_ms": 110},
            {"name": "Hybrid@30", "use_reranker": False, "recall_k": 30, "recall_at_k": 0.83, "total_latency_ms": 100},
        ]
    )
    assert tied["latency_first"] == "Hybrid@10"
    assert tied["adopted"] == "Hybrid@10"


def test_hit_at_k_is_alias_of_recall_and_markdown_omits_duplicate(tmp_path: Path):
    from src.config.settings import Settings
    from src.eval.runner import _aggregate_rows, _render_markdown, write_candidate_k_summary

    rows = [
        {
            "question": "Scholarship page?",
            "hit_doc": True,
            "hit_page": True,
            "hit_page_strict": True,
            "retrieval_mode": "hybrid",
            "recall_k": 20,
            "candidate_count": 20,
            "top_k": 5,
            "use_reranker": False,
            "use_bm25": True,
        }
    ]
    metrics = _aggregate_rows(rows, elapsed_ms=1.0, skip_generation=True)
    assert metrics["hit_at_k"] == metrics["recall_at_k"]
    assert metrics["hit_at_k_is_alias_of_recall_at_k"] is True
    assert metrics["eval_protocol"]["hit_at_k"].startswith("alias")
    settings = Settings(
        VECTOR_DB_PATH=str(tmp_path / "chroma"),
        BM25_STORE_PATH=str(tmp_path / "bm25.json"),
        DOC_REGISTRY_PATH=str(tmp_path / "registry.json"),
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        UPLOAD_CACHE_DIR=str(tmp_path / "uploads"),
    )
    md = _render_markdown(metrics, rows, settings)
    assert "hit_at_k` 是 `recall_at_k` 的别名" in md or "hit_at_k 是 `recall_at_k` 的别名" in md
    assert "- Hit@" not in md
    write_candidate_k_summary(
        {
            "hybrid20": {
                "metrics": {
                    **metrics,
                    "sample_count": 1,
                    "retrieval_latency_ms": 1.0,
                    "rerank_latency_ms": 0.0,
                    "total_latency_ms": 1.0,
                    "citation_page_hits": 1,
                    "strict_citation_hits": 1,
                }
            }
        },
        tmp_path / "summary.md",
        tmp_path / "summary.json",
    )
    table = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "| Hit@5 |" not in table
    assert "| Recall@5 |" in table


def test_candidate_k_ablation_runs_each_k_and_writes_new_dir(tmp_path: Path):
    from langchain_core.documents import Document

    from src.config.settings import Settings
    from src.eval.runner import run_candidate_k_ablation
    from src.services.qa_service import QAService

    questions = [
        {
            "id": "q1",
            "question": "How many leave days?",
            "expected_filename": "handbook.pdf",
            "expected_page_hint": 2,
        }
    ]
    qpath = tmp_path / "questions.json"
    qpath.write_text(json.dumps(questions), encoding="utf-8")

    def _docs(k: int, gold_index: int) -> list[Document]:
        out = []
        for i in range(k):
            is_gold = i == gold_index
            out.append(
                Document(
                    page_content="15 days" if is_gold else f"noise-{i}",
                    metadata={
                        "chunk_id": f"c{i}",
                        "doc_id": "d-gold" if is_gold else f"d{i}",
                        "filename": "handbook.pdf" if is_gold else "other.pdf",
                        "page": 2 if is_gold else i,
                    },
                )
            )
        return out

    def fake_retrieve(question: str, k: int | None = None) -> list[Document]:
        kk = int(k or 20)
        if kk <= 10:
            return _docs(kk, gold_index=-1)
        if kk == 20:
            return _docs(20, gold_index=6)
        return _docs(kk, gold_index=0)

    settings = Settings(
        VECTOR_DB_PATH=str(tmp_path / "chroma"),
        BM25_STORE_PATH=str(tmp_path / "bm25.json"),
        DOC_REGISTRY_PATH=str(tmp_path / "registry.json"),
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        UPLOAD_CACHE_DIR=str(tmp_path / "uploads"),
        USE_CONVERSATION_MEMORY=False,
        USE_RERANKER=False,
        USE_BM25=True,
        RETRIEVAL_MODE="hybrid",
        TOP_K=5,
        RECALL_TOP_N=20,
    )
    qa = QAService(settings)
    qa.retrieve_candidates = MagicMock(side_effect=fake_retrieve)  # type: ignore[method-assign]
    gold20 = fake_retrieve("q", k=20)[6]
    qa.reranker.rerank = MagicMock(return_value=[gold20])  # type: ignore[method-assign]

    out_dir = tmp_path / "candidate_k"
    original = tmp_path / "recall_hybrid20.json"
    original.write_text("{}", encoding="utf-8")
    result = run_candidate_k_ablation(
        qpath,
        qa_service=qa,
        settings=settings,
        out_dir=out_dir,
    )
    assert original.read_text(encoding="utf-8") == "{}"
    assert (out_dir / "hybrid10.json").exists()
    assert (out_dir / "hybrid20.json").exists()
    assert (out_dir / "hybrid30.json").exists()
    assert (out_dir / "hybrid20_rerank.json").exists()
    assert (out_dir / "summary.md").exists()
    p10 = result["payloads"]["hybrid10"]
    p20 = result["payloads"]["hybrid20"]
    p30 = result["payloads"]["hybrid30"]
    pr = result["payloads"]["hybrid20_rerank"]
    assert p10["metrics"]["recall_k"] == 10
    assert p20["metrics"]["recall_k"] == 20
    assert p30["metrics"]["recall_k"] == 30
    assert p10["metrics"]["use_reranker"] is False
    assert pr["metrics"]["use_reranker"] is True
    assert p10["rows"][0]["hit_doc"] is False
    assert p20["rows"][0]["hit_doc"] is False
    assert p30["rows"][0]["hit_doc"] is True
    assert pr["rows"][0]["hit_doc"] is True
    assert pr["rows"][0]["candidate_chunk_ids"] == p20["rows"][0]["candidate_chunk_ids"]
    assert p10["metrics"]["sample_count"] == 1
    assert p10["metrics"]["elapsed_ms"] == p10["metrics"]["retrieval_latency_ms"]
    assert pr["metrics"]["elapsed_ms"] == round(
        pr["metrics"]["retrieval_latency_ms"] + pr["metrics"]["rerank_latency_ms"],
        2,
    )
    assert result["summary"]["recommendation"]["latency_first"] == "Hybrid@30"
    called_ks = [c.kwargs.get("k") for c in qa.retrieve_candidates.call_args_list]
    assert called_ks[1:] == [10, 20, 30]
    qa.reranker.rerank.assert_called_once()

