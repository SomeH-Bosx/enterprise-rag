"""Phase4 API contract tests (upload / chat product shape)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app
from src.generation.schemas import ChatAnswer


client = TestClient(app)


def test_chat_accepts_query_and_returns_answer_sources():
    fake = {
        "answer": "年假 15 天。",
        "citations": [
            {
                "doc_id": "acme_1",
                "page": 1,
                "source": "acme_employee_handbook.pdf",
                "snippet": "15 days annual leave",
            }
        ],
        "mode": "dense_rerank",
        "query_type": "knowledge_query",
        "route_method": "rules",
        "route": "knowledge_query",
        "confidence": 88,
        "confidence_percent": 88,
        "confidence_level": "High",
        "model": "Ollama:qwen2.5:7b",
        "conversation_id": "abc123",
        "memory": {"enabled": True, "stored_messages": 2},
        "retrieved_docs": [
            {
                "filename": "acme_employee_handbook.pdf",
                "doc_id": "acme_1",
                "page": 1,
                "score": 0.81,
                "rank": 1,
                "snippet": "15 days",
            }
        ],
        "reranked_docs": [
            {
                "filename": "acme_employee_handbook.pdf",
                "doc_id": "acme_1",
                "page": 1,
                "score": 0.91,
                "rank": 1,
                "snippet": "15 days",
            }
        ],
        "trace": {
            "route": "knowledge_query",
            "query_type": "knowledge_query",
            "route_method": "rules",
            "mode": "dense_rerank",
            "retrieval": {"retriever": "Chroma Dense Similarity", "top_k": 20, "documents": ["acme_employee_handbook.pdf"]},
            "reranking": {"reranker": "DashScope Reranker", "selected_top_n": 5, "documents": ["acme_employee_handbook.pdf"]},
            "generation": {"llm": "Ollama:qwen2.5:7b", "status": "Response Generated"},
            "confidence": {"score": 0.88, "percent": 88, "level": "High", "factors": {}},
            "retrieved_docs": [],
            "reranked_docs": [],
            "model": "Ollama:qwen2.5:7b",
            "confidence_percent": 88,
            "confidence_level": "High",
        },
    }
    with patch("apps.api.main.qa_service.ask", return_value=fake):
        resp = client.post(
            "/chat",
            json={"query": "公司的年假政策是什么？", "conversation_id": "abc123"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "年假 15 天。"
    assert isinstance(data["sources"], list)
    assert data["sources"][0]["filename"] == "acme_employee_handbook.pdf"
    assert data["query_type"] == "knowledge_query"
    assert data["route"] == "knowledge_query"
    assert data["confidence_percent"] == 88
    assert data["confidence_level"] == "High"
    assert data["model"].startswith("Ollama:")
    assert data["trace"] is not None
    assert data["trace"]["retrieval"]["top_k"] == 20
    assert data["trace"]["reranking"]["reranker"] == "DashScope Reranker"
    assert data["conversation_id"] == "abc123"
    assert data["memory"]["enabled"] is True


def test_chat_accepts_legacy_question_field():
    fake = ChatAnswer(
        final_answer="你好，我是企业知识库助手。",
        reasoning_summary="casual_chat: skipped retrieval",
        citations=[],
        route_reason="casual_chat:rules",
    )
    with patch("apps.api.main.qa_service.ask", return_value=fake):
        resp = client.post("/chat", json={"question": "你好，你是谁？"})
    assert resp.status_code == 200
    data = resp.json()
    assert "助手" in data["answer"] or data["answer"]
    assert data["sources"] == []
    assert data["query_type"] == "casual_chat"


def test_upload_rejects_unsupported_type():
    resp = client.post(
        "/upload",
        files={"file": ("sheet.xlsx", b"not-excel", "application/vnd.ms-excel")},
    )
    assert resp.status_code == 400
    assert resp.json().get("ok") is False


def test_upload_success_shape():
    fake_result = {
        "filename": "demo.pdf",
        "doc_id": "demo_abc",
        "chunk_count": 3,
        "file_type": "pdf",
    }
    with patch("apps.api.main.ingest_service.ingest_file", return_value=fake_result):
        resp = client.post(
            "/upload",
            files={"file": ("demo.pdf", b"%PDF-1.4 demo", "application/pdf")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "indexed"
    assert data["filename"] == "demo.pdf"
    assert data["chunk_count"] == 3


def test_upload_accepts_txt():
    fake_result = {
        "filename": "notes.txt",
        "doc_id": "notes_abc",
        "chunk_count": 1,
        "file_type": "txt",
    }
    with patch("apps.api.main.ingest_service.ingest_file", return_value=fake_result):
        resp = client.post(
            "/upload",
            files={"file": ("notes.txt", b"hello knowledge base", "text/plain")},
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["file_type"] == "txt"
