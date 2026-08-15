from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


def bypass_local_proxy() -> None:
    """Keep localhost Ollama traffic off system HTTP proxies (avoids 502 via httpx)."""
    for key in ("NO_PROXY", "no_proxy"):
        existing = {p.strip() for p in os.environ.get(key, "").split(",") if p.strip()}
        existing.update({"127.0.0.1", "localhost", "::1"})
        os.environ[key] = ",".join(sorted(existing))


bypass_local_proxy()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    llm_model: str = Field(default="qwen2.5:7b", alias="LLM_MODEL")
    embed_model: str = Field(default="nomic-embed-text", alias="EMBED_MODEL")
    vector_db_path: str = Field(default=str(ROOT_DIR / "chroma_db"), alias="VECTOR_DB_PATH")
    upload_cache_dir: str = Field(default=str(ROOT_DIR / "upload_cache"), alias="UPLOAD_CACHE_DIR")
    bm25_store_path: str = Field(
        default=str(ROOT_DIR / "chroma_db" / "bm25_store.json"),
        alias="BM25_STORE_PATH",
    )
    doc_registry_path: str = Field(
        default=str(ROOT_DIR / "chroma_db" / "doc_registry.json"),
        alias="DOC_REGISTRY_PATH",
    )
    chunk_size: int = Field(default=1000, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=150, alias="CHUNK_OVERLAP")
    top_k: int = Field(default=5, alias="TOP_K")
    recall_top_n: int = Field(default=20, alias="RECALL_TOP_N")
    # Phase2 enables reranker by default. BM25 Hybrid: implement but default OFF (Step3.5).
    use_bm25: bool = Field(default=False, alias="USE_BM25")
    # dense | bm25 | hybrid — empty means derive from USE_BM25 (true→hybrid, else dense).
    retrieval_mode: str = Field(default="", alias="RETRIEVAL_MODE")
    use_reranker: bool = Field(default=True, alias="USE_RERANKER")
    use_pdr: bool = Field(default=False, alias="USE_PDR")
    # Phase3 Query Router: classify intent before retrieval.
    use_query_router: bool = Field(default=True, alias="USE_QUERY_ROUTER")
    # rules | llm | rules_llm (rules first, LLM on ambiguous)
    query_router_mode: str = Field(default="rules_llm", alias="QUERY_ROUTER_MODE")
    # Step3.5 Query Rewrite (retrieval query only; answer still uses original)
    use_query_rewrite: bool = Field(default=True, alias="USE_QUERY_REWRITE")
    # rules | llm | rules_llm
    query_rewrite_mode: str = Field(default="rules_llm", alias="QUERY_REWRITE_MODE")
    reranker_model: str = Field(default="BAAI/bge-reranker-base", alias="RERANKER_MODEL")
    # dashscope | cross_encoder | lexical | auto
    reranker_backend: str = Field(default="dashscope", alias="RERANKER_BACKEND")
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    dashscope_rerank_model: str = Field(default="gte-rerank-v2", alias="DASHSCOPE_RERANK_MODEL")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    collection_name: str = Field(default="enterprise_rag", alias="COLLECTION_NAME")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    # Phase4 productization
    api_base_url: str = Field(default="http://127.0.0.1:8000", alias="API_BASE_URL")
    streamlit_port: int = Field(default=8501, alias="STREAMLIT_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # Step3 Conversation Memory
    use_conversation_memory: bool = Field(default=True, alias="USE_CONVERSATION_MEMORY")
    memory_max_turns: int = Field(default=6, alias="MEMORY_MAX_TURNS")
    memory_max_chars: int = Field(default=3000, alias="MEMORY_MAX_CHARS")
    conversation_store_path: str = Field(
        default=str(ROOT_DIR / "chroma_db" / "conversations.json"),
        alias="CONVERSATION_STORE_PATH",
    )
    # Step3.6 table serialization + OCR (pytesseract / system Tesseract)
    enable_table_serialization: bool = Field(
        default=True,
        alias="ENABLE_TABLE_SERIALIZATION",
    )
    enable_ocr: bool = Field(default=True, alias="ENABLE_OCR")
    ocr_lang: str = Field(default="chi_sim+eng", alias="OCR_LANG")
    ocr_min_text_chars: int = Field(default=40, alias="OCR_MIN_TEXT_CHARS")
    ocr_dpi: int = Field(default=200, alias="OCR_DPI")

    def ensure_dirs(self) -> None:
        Path(self.vector_db_path).mkdir(parents=True, exist_ok=True)
        Path(self.upload_cache_dir).mkdir(parents=True, exist_ok=True)
        Path(self.bm25_store_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.doc_registry_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.conversation_store_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
