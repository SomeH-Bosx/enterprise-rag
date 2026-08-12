"""Unit tests for Answer Trace confidence scoring."""

from __future__ import annotations

from langchain_core.documents import Document

from src.generation.trace import (
    build_answer_trace,
    compute_chunk_confidence,
    compute_confidence,
    distance_to_similarity,
)


def test_distance_to_similarity_monotone():
    assert distance_to_similarity(0) == 1.0
    assert distance_to_similarity(1) == 0.5
    a = distance_to_similarity(0.1)
    b = distance_to_similarity(2.0)
    assert a is not None and b is not None
    assert a > b


def test_confidence_knowledge_high_when_signals_strong():
    result = compute_confidence(
        query_type="knowledge_query",
        retrieved=True,
        answer="根据员工手册，年假为 15 天，适用于正式员工。",
        retrieval_scores=[0.82, 0.78, 0.71],
        rerank_scores=[0.93, 0.88, 0.81],
        source_count=1,
        expected_sources=1,
    )
    assert result["percent"] >= 65
    assert result["level"] == "High"
    assert result["factors"]["rerank"] is not None
    assert "formula" in result["factors"]


def test_confidence_mid_band_can_reach_high_after_calibration():
    """Calibrated thresholds + top-heavy scores should feel more intuitive."""
    result = compute_confidence(
        query_type="knowledge_query",
        retrieved=True,
        answer="年假政策为每年 15 天带薪休假，详情见员工手册条款。",
        retrieval_scores=[0.62, 0.55],
        rerank_scores=[0.86, 0.80],
        source_count=1,
        expected_sources=1,
    )
    assert result["percent"] >= 65
    assert result["level"] == "High"


def test_confidence_refusal_is_lower():
    strong = compute_confidence(
        query_type="knowledge_query",
        retrieved=True,
        answer="年假政策为每年 15 天带薪休假，详情见员工手册。",
        retrieval_scores=[0.8],
        rerank_scores=[0.9],
        source_count=1,
    )
    weak = compute_confidence(
        query_type="knowledge_query",
        retrieved=True,
        answer="文档中未找到相关内容。",
        retrieval_scores=[0.8],
        rerank_scores=[0.9],
        source_count=1,
    )
    assert weak["percent"] < strong["percent"]


def test_confidence_casual_moderate():
    result = compute_confidence(
        query_type="casual_chat",
        retrieved=False,
        answer="你好，我是企业知识库助手。",
    )
    assert result["level"] == "Medium"
    assert 40 <= result["percent"] <= 70


def test_chunk_confidence_formula():
    out = compute_chunk_confidence(0.72, 0.90)
    assert out["chunk_confidence"] is not None
    assert abs(out["chunk_confidence"] - (0.4 * 0.72 + 0.6 * 0.90)) < 1e-6
    assert "0.4" in out["formula"] and "0.6" in out["formula"]


def test_build_answer_trace_shape():
    candidates = [
        Document(
            page_content="annual leave 15 days",
            metadata={
                "filename": "acme.pdf",
                "doc_id": "d1",
                "page": 1,
                "retrieval_score": 0.8,
            },
        )
    ]
    ranked = [
        Document(
            page_content="annual leave 15 days",
            metadata={
                "filename": "acme.pdf",
                "doc_id": "d1",
                "page": 1,
                "retrieval_score": 0.8,
                "rerank_score": 0.92,
                "rerank_rank": 1,
            },
        )
    ]
    trace = build_answer_trace(
        query_type="knowledge_query",
        route_method="rules",
        mode="dense_rerank",
        retrieved=True,
        answer="年假 15 天。",
        candidates=candidates,
        ranked=ranked,
        recall_k=20,
        top_n=5,
        use_reranker=True,
        reranker_backend="dashscope",
        llm_model="qwen2.5:7b",
        embed_model="nomic-embed-text",
    )
    assert trace["route"] == "knowledge_query"
    assert trace["retrieval"]["top_k"] == 20
    assert "acme.pdf" in trace["retrieval"]["documents"]
    assert trace["reranking"]["reranker"] == "DashScope Reranker"
    assert trace["generation"]["llm"] == "Ollama:qwen2.5:7b"
    assert "percent" in trace["confidence"]
    assert isinstance(trace["retrieved_docs"], list)
    assert isinstance(trace["reranked_docs"], list)
    item = trace["reranked_docs"][0]
    assert item.get("chunk_confidence") is not None
    assert item.get("confidence_formula")
    blob = str(trace)
    assert "DASHSCOPE" not in blob
    assert "api_key" not in blob.lower()
    assert "system prompt" not in blob.lower()
