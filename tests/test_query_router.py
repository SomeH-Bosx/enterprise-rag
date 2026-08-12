"""Phase3 Query Router tests: intent classification + chain routing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import Settings, get_settings
from src.router import QueryRouter, route_query_intent
from src.router.classifier import classify_by_rules, classify_query
from src.services.exceptions import NoIndexError
from src.services.qa_service import QAService


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(**kwargs) -> Settings:
    base = dict(
        use_query_router=True,
        query_router_mode="rules_llm",
        use_reranker=True,
        reranker_backend="lexical",
    )
    base.update(kwargs)
    return Settings(**base)


def test_case1_knowledge_query_classification():
    """案例1：知识库问题应进入 knowledge_query。"""
    question = "公司的年假政策是什么？"
    assert classify_by_rules(question) == "knowledge_query"
    result = route_query_intent(question, _settings())
    assert result["query_type"] == "knowledge_query"
    assert result["enabled"] is True


def test_case2_casual_chat_classification():
    """案例2：闲聊问题应进入 casual_chat。"""
    question = "你好，你是谁？"
    assert classify_by_rules(question) == "casual_chat"
    result = route_query_intent(question, _settings())
    assert result["query_type"] == "casual_chat"


def test_casual_chat_skips_retrieval():
    """闲聊路径：不进入 Retriever / Reranker。"""
    settings = _settings()
    qa = QAService(settings)
    qa.retrieve = MagicMock(side_effect=AssertionError("retrieve must not be called"))
    qa.retrieve_with_rerank = MagicMock(
        side_effect=AssertionError("retrieve_with_rerank must not be called")
    )
    qa._ensure_index = MagicMock(side_effect=AssertionError("index check must not run"))

    with patch(
        "src.services.qa_service.invoke_text",
        return_value="我是企业知识库问答助手。",
    ) as mock_llm:
        answer = qa.ask("你好，你是谁？", structured=False)

    mock_llm.assert_called_once()
    assert answer["query_type"] == "casual_chat"
    assert answer["mode"] == "casual_chat"
    assert answer["retrieved"] is False
    assert answer["use_reranker"] is False
    assert answer["citations"] == []
    assert "助手" in answer["answer"]


def test_knowledge_query_enters_retrieve_rerank_path(tmp_path):
    """知识库问题：走 Retriever → Reranker → LLM（检索被调用）。"""
    settings = _settings(
        vector_db_path=str(tmp_path / "chroma"),
        upload_cache_dir=str(tmp_path / "uploads"),
        bm25_store_path=str(tmp_path / "bm25.json"),
        doc_registry_path=str(tmp_path / "docs.json"),
    )
    from src.services.ingest_service import IngestService

    pdf = Path(__file__).resolve().parents[1] / "data" / "samples" / "acme_employee_handbook.pdf"
    assert pdf.exists()
    ingest = IngestService(settings)
    ingest.ingest_pdf(pdf)

    qa = QAService(
        settings,
        vector_store=ingest.vector_store,
        bm25_store=ingest.bm25_store,
        registry=ingest.registry,
    )

    with patch(
        "src.services.qa_service.invoke_text",
        return_value="年假 15 天。",
    ):
        answer = qa.ask("公司的年假政策是什么？", structured=False)

    assert answer["query_type"] == "knowledge_query"
    assert answer["retrieved"] is True
    assert answer["mode"] in ("dense_rerank", "naive")
    assert answer["final_count"] >= 1


def test_casual_chat_works_without_index(tmp_path):
    """闲聊在无索引时也不应抛 NoIndexError。"""
    settings = _settings(
        vector_db_path=str(tmp_path / "chroma"),
        upload_cache_dir=str(tmp_path / "uploads"),
        bm25_store_path=str(tmp_path / "bm25.json"),
        doc_registry_path=str(tmp_path / "docs.json"),
    )
    qa = QAService(settings)
    with patch("src.services.qa_service.invoke_text", return_value="你好！"):
        answer = qa.ask("你好，你是谁？")
    assert answer["query_type"] == "casual_chat"


def test_knowledge_query_still_requires_index(tmp_path):
    settings = _settings(
        vector_db_path=str(tmp_path / "chroma"),
        upload_cache_dir=str(tmp_path / "uploads"),
        bm25_store_path=str(tmp_path / "bm25.json"),
        doc_registry_path=str(tmp_path / "docs.json"),
    )
    qa = QAService(settings)
    with pytest.raises(NoIndexError):
        qa.ask("公司的年假政策是什么？")


def test_router_disabled_always_knowledge():
    settings = _settings(use_query_router=False)
    result = QueryRouter(settings).route("你好，你是谁？")
    assert result.query_type == "knowledge_query"
    assert result.method == "disabled"
    assert result.enabled is False


def test_classify_query_llm_fallback_on_ambiguous():
    settings = _settings(query_router_mode="rules_llm")
    with patch(
        "src.router.classifier.invoke_text",
        return_value='{"query_type":"casual_chat"}',
    ):
        label, method = classify_query("随便聊聊", settings)
    assert label == "casual_chat"
    assert method == "llm"
