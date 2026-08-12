from __future__ import annotations

from langchain_core.documents import Document

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.reranker.base import BaseReranker
from src.reranker.cross_encoder import CrossEncoderReranker as LocalCrossEncoderReranker
from src.reranker.dashscope_reranker import DashScopeReranker
from src.reranker.lexical import LexicalReranker

logger = get_logger("reranker_facade")


class Reranker(BaseReranker):
    """
    Backend-selecting facade. Upper layers keep calling `.rerank(...)`.
    Backends: dashscope (default) | cross_encoder | lexical | auto
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._lexical = LexicalReranker()

    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        backend = (self.settings.reranker_backend or "dashscope").strip().lower()
        logger.info("reranker_backend_selected", backend=backend, top_n=top_n, candidates=len(documents))

        if backend == "lexical":
            return self._lexical.rerank(query, documents, top_n=top_n)

        if backend == "cross_encoder":
            return LocalCrossEncoderReranker(self.settings).rerank(query, documents, top_n=top_n)

        if backend in {"dashscope", "auto"}:
            # auto: prefer dashscope when key exists, else cross_encoder then lexical
            if self.settings.dashscope_api_key.strip():
                return DashScopeReranker(self.settings).rerank(query, documents, top_n=top_n)
            if backend == "dashscope":
                logger.warning("dashscope_selected_but_no_api_key_fallback_lexical")
                return self._lexical.rerank(query, documents, top_n=top_n)
            # auto without key
            logger.info("auto_backend_without_dashscope_key_try_cross_encoder")
            return LocalCrossEncoderReranker(self.settings).rerank(query, documents, top_n=top_n)

        logger.warning("unknown_reranker_backend_fallback_lexical", backend=backend)
        return self._lexical.rerank(query, documents, top_n=top_n)
