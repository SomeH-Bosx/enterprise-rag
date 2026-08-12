from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.config.settings import Settings, get_settings
from src.reranker.dashscope_reranker import DashScopeReranker
from src.services.ingest_service import IngestService
from src.services.qa_service import QAService


def test_rag_flow_retriever_dashscope_reranker_llm(tmp_path):
    """
    Integration-style flow:
    Query -> Retriever -> DashScope Reranker (mocked) -> LLM (mocked)
    """
    get_settings.cache_clear()
    settings = Settings(
        vector_db_path=str(tmp_path / "chroma"),
        upload_cache_dir=str(tmp_path / "uploads"),
        bm25_store_path=str(tmp_path / "bm25.json"),
        doc_registry_path=str(tmp_path / "docs.json"),
        use_reranker=True,
        reranker_backend="dashscope",
        dashscope_api_key="sk-test",
        recall_top_n=20,
        top_k=5,
    )

    root = Path(__file__).resolve().parents[1]
    pdf_beta = root / "data" / "samples" / "beta_product_spec.pdf"
    pdf_mix = root / "data" / "samples" / "enterprise_knowledge_mix.pdf"
    assert pdf_beta.exists(), "sample PDF missing; run scripts/make_sample_pdfs.py"

    ingest = IngestService(settings)
    ingest.ingest_pdf(pdf_beta)
    if pdf_mix.exists():
        ingest.ingest_pdf(pdf_mix)

    qa = QAService(
        settings,
        vector_store=ingest.vector_store,
        bm25_store=ingest.bm25_store,
        registry=ingest.registry,
        reranker=DashScopeReranker(settings, enable_fallback=False),
    )

    question = "What is the p95 latency SLO for Nebula Search Appliance?"

    def _fake_call(**kwargs):
        docs = kwargs.get("documents") or []
        scored = []
        for i, text in enumerate(docs):
            score = 0.1
            low = (text or "").lower()
            if "p95" in low or "latency" in low or "200 milliseconds" in low:
                score = 0.95
            scored.append({"index": i, "relevance_score": score})
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return SimpleNamespace(status_code=200, output={"results": scored})

    with patch("dashscope.TextReRank.call", side_effect=_fake_call), patch(
        "src.services.qa_service.invoke_text",
        return_value="p95 query latency under 200 milliseconds.",
    ):
        answer = qa.ask(question, structured=False)

    assert answer["use_reranker"] is True
    assert answer["mode"] == "dense_rerank"
    assert "200" in answer["answer"]
    assert answer["final_count"] <= settings.top_k
