"""Phase5 eval unit tests (no live Ollama required)."""

from __future__ import annotations

from src.eval.ragas_lite import (
    aggregate_ragas_style,
    answer_relevancy_score,
    faithfulness_score,
    must_include_pass,
    score_row,
)
from src.eval.recall import aggregate_recall, recall_hit


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
