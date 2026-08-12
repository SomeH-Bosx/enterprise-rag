"""Step3.5 Query Rewrite / Hybrid unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from src.config.settings import Settings
from src.indexing.bm25_store import BM25Store
from src.memory.store import Message
from src.query_rewrite.rewriter import QueryRewriter
from src.retrieval.hybrid import hybrid_retrieve, rrf_fuse
from src.services.qa_service import QAService


def _settings(tmp_path: Path, **kwargs) -> Settings:
    base = dict(
        VECTOR_DB_PATH=str(tmp_path / "chroma"),
        BM25_STORE_PATH=str(tmp_path / "bm25.json"),
        DOC_REGISTRY_PATH=str(tmp_path / "registry.json"),
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        UPLOAD_CACHE_DIR=str(tmp_path / "uploads"),
        USE_CONVERSATION_MEMORY=True,
        USE_QUERY_ROUTER=True,
        USE_QUERY_REWRITE=True,
        QUERY_REWRITE_MODE="rules_llm",
        USE_BM25=False,
        USE_RERANKER=False,
    )
    base.update(kwargs)
    return Settings(**base)


def test_rule_rewrite_followup():
    settings = Settings(USE_QUERY_REWRITE=True, QUERY_REWRITE_MODE="rules")
    rewriter = QueryRewriter(settings)
    history = [
        Message(role="user", content="公司年假政策是什么？"),
        Message(role="assistant", content="15天"),
    ]
    result = rewriter.rewrite("那病假呢？", history)
    assert result.method == "rules"
    assert "年假" in result.rewritten_query or "病假" in result.rewritten_query
    assert result.original_query == "那病假呢？"
    assert result.used_rewrite is True


def test_rewrite_llm_success(tmp_path: Path):
    settings = _settings(tmp_path, QUERY_REWRITE_MODE="llm")
    rewriter = QueryRewriter(settings)
    history = [Message(role="user", content="Acme annual leave days?")]
    with patch(
        "src.query_rewrite.rewriter.invoke_text",
        return_value="Acme company sick leave policy days",
    ):
        result = rewriter.rewrite("what about sick leave?", history)
    assert result.method == "llm"
    assert "sick leave" in result.rewritten_query.lower()
    assert result.original_query == "what about sick leave?"


def test_rewrite_llm_failure_falls_back_to_memory(tmp_path: Path):
    settings = _settings(tmp_path, QUERY_REWRITE_MODE="llm")
    rewriter = QueryRewriter(settings)
    history = [Message(role="user", content="公司年假几天？")]
    with patch(
        "src.query_rewrite.rewriter.invoke_text",
        side_effect=RuntimeError("ollama down"),
    ):
        result = rewriter.rewrite("那病假呢？", history)
    assert result.method == "memory_fallback"
    assert "年假" in result.rewritten_query
    assert "病假" in result.rewritten_query
    assert result.used_rewrite is False


def test_rewrite_disabled_uses_memory_concat(tmp_path: Path):
    settings = _settings(tmp_path, USE_QUERY_REWRITE=False)
    rewriter = QueryRewriter(settings)
    history = [Message(role="user", content="年假政策")]
    result = rewriter.rewrite("病假呢", history)
    assert result.method == "memory_fallback"
    assert "年假" in result.rewritten_query
    assert result.used_rewrite is False


def test_hybrid_rrf_and_default_off(tmp_path: Path):
    settings = _settings(tmp_path, USE_BM25=True)
    bm25 = BM25Store(settings)
    docs = [
        Document(page_content="annual leave fifteen days", metadata={"chunk_id": "c1", "doc_id": "d1"}),
        Document(page_content="unrelated cafeteria menu", metadata={"chunk_id": "c2", "doc_id": "d1"}),
    ]
    bm25.upsert_documents(docs)

    class FakeVS:
        def similarity_search_with_score(self, query, k=5, doc_ids=None):
            return [
                (Document(page_content=docs[1].page_content, metadata=dict(docs[1].metadata)), 0.8),
                (Document(page_content=docs[0].page_content, metadata=dict(docs[0].metadata)), 1.2),
            ][:k]

        def similarity_search(self, query, k=5, doc_ids=None):
            return [d for d, _ in self.similarity_search_with_score(query, k=k, doc_ids=doc_ids)]

    fused = hybrid_retrieve(
        "annual leave days",
        FakeVS(),  # type: ignore[arg-type]
        bm25,
        settings=settings,
        use_bm25=True,
        recall_top_n=5,
    )
    assert fused
    assert fused[0].metadata.get("chunk_id") == "c1"
    assert fused[0].metadata.get("rrf_score") is not None

    dense_only = hybrid_retrieve(
        "annual leave days",
        FakeVS(),  # type: ignore[arg-type]
        bm25,
        settings=settings,
        use_bm25=False,
        recall_top_n=5,
    )
    assert dense_only[0].metadata.get("chunk_id") == "c2"  # dense order preserved when hybrid off


def test_qa_uses_rewritten_for_retrieve_original_for_prompt(tmp_path: Path):
    settings = _settings(tmp_path, USE_QUERY_REWRITE=True, QUERY_REWRITE_MODE="llm", USE_BM25=False)
    store_path = tmp_path / "conv.json"
    settings = _settings(
        tmp_path,
        CONVERSATION_STORE_PATH=str(store_path),
        USE_QUERY_REWRITE=True,
        QUERY_REWRITE_MODE="llm",
    )
    qa = QAService(settings=settings)
    qa.query_router = MagicMock()
    route = MagicMock()
    route.query_type = "knowledge_query"
    route.method = "rules"
    route.enabled = True
    qa.query_router.route.return_value = route

    qa._ensure_index = MagicMock()  # type: ignore[method-assign]
    ranked = [
        Document(
            page_content="Sick leave is 10 days.",
            metadata={"chunk_id": "1", "doc_id": "d1", "filename": "handbook.pdf", "page": 1, "retrieval_score": 0.9},
        )
    ]
    qa.retrieve = MagicMock(return_value=(ranked, {  # type: ignore[method-assign]
        "mode": "naive",
        "use_reranker": False,
        "use_hybrid": False,
        "candidate_count": 1,
        "final_count": 1,
        "recall_k": 5,
        "top_n": 5,
        "candidates": ranked,
    }))

    with patch(
        "src.query_rewrite.rewriter.invoke_text",
        return_value="公司病假天数政策",
    ), patch(
        "src.services.qa_service.invoke_text",
        return_value="病假 10 天。",
    ) as gen_mock:
        # seed memory with prior turn
        from src.memory import ConversationStore

        store = ConversationStore(settings)
        conv = store.get_or_create(None)
        store.append(conv.conversation_id, role="user", content="公司年假几天？")
        store.append(conv.conversation_id, role="assistant", content="15天")
        qa.conversation_store = store

        result = qa.ask("那病假呢？", structured=False, conversation_id=conv.conversation_id)

    assert isinstance(result, dict)
    # retrieval used rewritten query
    assert qa.retrieve.call_args[0][0] == "公司病假天数政策"
    # generation prompt still contains original follow-up
    prompt = gen_mock.call_args[0][0]
    assert "那病假呢？" in prompt
    assert result.get("original_query") == "那病假呢？"
    assert result.get("rewritten_query") == "公司病假天数政策"
    assert result.get("use_hybrid") is False
    assert result.get("trace", {}).get("original_query") == "那病假呢？"
    assert result.get("trace", {}).get("rewritten_query") == "公司病假天数政策"


def test_settings_field_defaults_for_step35():
    assert Settings.model_fields["use_bm25"].default is False
    assert Settings.model_fields["use_query_rewrite"].default is True


def test_rrf_fuse_still_prefers_overlap():
    d1 = Document(page_content="a", metadata={"chunk_id": "1"})
    d2 = Document(page_content="b", metadata={"chunk_id": "2"})
    d3 = Document(page_content="c", metadata={"chunk_id": "3"})
    fused = rrf_fuse([[d1, d2], [d2, d3]])
    assert fused[0].metadata["chunk_id"] == "2"
