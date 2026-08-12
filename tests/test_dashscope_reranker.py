from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

from src.reranker.dashscope_reranker import DashScopeReranker
from src.reranker.facade import Reranker
from src.config.settings import Settings


def _docs() -> list[Document]:
    return [
        Document(page_content="Parking permits are required in lot B.", metadata={"chunk_id": "noise"}),
        Document(
            page_content="Nebula Search Appliance latency SLO: p95 under 200 milliseconds.",
            metadata={"chunk_id": "signal"},
        ),
        Document(page_content="Cafeteria menu updates every Monday.", metadata={"chunk_id": "noise2"}),
    ]


def test_dashscope_reranker_changes_order_with_mocked_api():
    """Unit test: mocked DashScope scores put signal doc first."""
    fake_results = [
        {"index": 1, "relevance_score": 0.98},
        {"index": 0, "relevance_score": 0.11},
        {"index": 2, "relevance_score": 0.10},
    ]
    fake_resp = SimpleNamespace(status_code=200, output=SimpleNamespace(results=fake_results))

    settings = Settings(
        dashscope_api_key="sk-test",
        reranker_backend="dashscope",
        dashscope_rerank_model="gte-rerank-v2",
    )
    reranker = DashScopeReranker(settings, enable_fallback=False)

    with patch("dashscope.TextReRank.call", return_value=fake_resp):
        ranked = reranker.rerank(
            "What is the p95 latency SLO for Nebula Search Appliance?",
            _docs(),
            top_n=2,
        )

    assert [d.metadata["chunk_id"] for d in ranked] == ["signal", "noise"]
    assert ranked[0].metadata["reranker"] == "dashscope"
    assert ranked[0].metadata["rerank_rank"] == 1
    # Order changed vs original candidate order (noise, signal, noise2)
    assert ranked[0].metadata["chunk_id"] != _docs()[0].metadata["chunk_id"]


def test_dashscope_missing_key_falls_back_to_lexical():
    settings = Settings(dashscope_api_key="", reranker_backend="dashscope")
    reranker = DashScopeReranker(settings, enable_fallback=True)
    ranked = reranker.rerank(
        "What is the p95 latency SLO for Nebula Search Appliance?",
        _docs(),
        top_n=2,
    )
    assert ranked[0].metadata["chunk_id"] == "signal"
    assert ranked[0].metadata.get("reranker") in {"lexical", "lexical_fallback"}


def test_facade_uses_dashscope_backend_when_configured():
    settings = Settings(
        dashscope_api_key="sk-test",
        reranker_backend="dashscope",
    )
    fake_results = [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]
    fake_resp = SimpleNamespace(status_code=200, output={"results": fake_results})
    facade = Reranker(settings)
    with patch("dashscope.TextReRank.call", return_value=fake_resp):
        ranked = facade.rerank("p95 latency Nebula", _docs(), top_n=1)
    assert ranked[0].metadata["chunk_id"] == "signal"
    assert ranked[0].metadata["reranker"] == "dashscope"
