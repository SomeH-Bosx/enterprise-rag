"""Step4 session model configuration tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config.session_models import SessionModelOverrides, defaults_from_settings
from src.config.settings import Settings
from src.services.qa_service import QAService


def test_overrides_apply_without_touching_env_defaults():
    base = Settings(
        LLM_MODEL="qwen2.5:7b",
        EMBED_MODEL="nomic-embed-text",
        RERANKER_BACKEND="dashscope",
    )
    ov = SessionModelOverrides(
        llm_model="llama3.2:3b",
        embed_model="nomic-embed-text",
        reranker_backend="lexical",
    )
    eff = ov.apply(base)
    assert eff.llm_model == "llama3.2:3b"
    assert eff.reranker_backend == "lexical"
    assert base.llm_model == "qwen2.5:7b"
    assert base.reranker_backend == "dashscope"


def test_overrides_apply_retrieval_mode():
    base = Settings(USE_BM25=False, RETRIEVAL_MODE="")
    ov = SessionModelOverrides(retrieval_mode="hybrid")
    eff = ov.apply(base)
    assert eff.retrieval_mode == "hybrid"
    assert base.retrieval_mode == ""


def test_strip_ollama_prefix_and_reject_bad_backend():
    ov = SessionModelOverrides.from_mapping(
        {
            "llm_model": "Ollama:qwen2.5:7b",
            "reranker_backend": "not-a-backend",
        }
    )
    assert ov.llm_model == "qwen2.5:7b"
    assert ov.reranker_backend is None


def test_defaults_from_settings_no_secrets():
    s = Settings(DASHSCOPE_API_KEY="sk-secret-should-not-leak")
    d = defaults_from_settings(s)
    assert "dashscope_api_key" not in d
    assert set(d) == {
        "llm_model",
        "embed_model",
        "reranker_backend",
        "retrieval_mode",
        "use_conversation_memory",
    }
    blob = str(d)
    assert "sk-secret" not in blob


def test_overrides_apply_memory_flag():
    base = Settings(USE_CONVERSATION_MEMORY=True)
    ov = SessionModelOverrides(use_conversation_memory=False)
    eff = ov.apply(base)
    assert eff.use_conversation_memory is False
    assert base.use_conversation_memory is True


def test_qa_ask_uses_session_llm(tmp_path: Path):
    settings = Settings(
        VECTOR_DB_PATH=str(tmp_path / "chroma"),
        BM25_STORE_PATH=str(tmp_path / "bm25.json"),
        DOC_REGISTRY_PATH=str(tmp_path / "registry.json"),
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        UPLOAD_CACHE_DIR=str(tmp_path / "uploads"),
        USE_CONVERSATION_MEMORY=False,
        USE_QUERY_REWRITE=False,
        LLM_MODEL="base-llm",
        RERANKER_BACKEND="lexical",
    )
    qa = QAService(settings=settings)
    qa.query_router = MagicMock()
    route = MagicMock()
    route.query_type = "casual_chat"
    route.method = "rules"
    route.enabled = True
    qa.query_router.route.return_value = route

    with patch("src.services.qa_service.invoke_text", return_value="hi") as mocked:
        # Also patch rewriter path unused for casual
        result = qa.ask(
            "你好",
            structured=False,
            model_overrides={"llm_model": "session-llm"},
        )
    assert isinstance(result, dict)
    # invoke_text called with overridden settings
    cfg = mocked.call_args[0][1] if len(mocked.call_args[0]) > 1 else mocked.call_args.kwargs.get("settings")
    assert cfg is not None
    assert cfg.llm_model == "session-llm"
    assert settings.llm_model == "base-llm"
    assert result.get("session_models", {}).get("effective", {}).get("llm_model") == "session-llm"
