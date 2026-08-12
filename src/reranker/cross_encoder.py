from __future__ import annotations

from functools import lru_cache

from langchain_core.documents import Document

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.reranker.base import BaseReranker
from src.reranker.lexical import LexicalReranker

logger = get_logger("reranker")


@lru_cache
def _load_cross_encoder(model_name: str):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


class CrossEncoderReranker(BaseReranker):
    """
    Prefer CrossEncoder (BAAI/bge-reranker-base).
    If model download/load fails, fall back to LexicalReranker so Phase2 still works offline.
    """

    def __init__(self, settings: Settings | None = None, model_name: str | None = None):
        self.settings = settings or get_settings()
        self.model_name = model_name or self.settings.reranker_model
        self.backend = (getattr(self.settings, "reranker_backend", "auto") or "auto").lower()
        self._model = None
        self._failed = False
        self._fallback = LexicalReranker()
        self._active_backend = "uninitialized"

    def _get_model(self):
        if self.backend == "lexical":
            self._active_backend = "lexical"
            return None
        if self.backend == "cross_encoder" or self.backend == "auto":
            if self._failed:
                return None
            if self._model is None:
                try:
                    logger.info("reranker_loading", model=self.model_name, backend="cross_encoder")
                    self._model = _load_cross_encoder(self.model_name)
                    self._active_backend = "cross_encoder"
                    logger.info("reranker_loaded", model=self.model_name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "reranker_load_failed_use_lexical_fallback",
                        error=str(exc),
                        model=self.model_name,
                    )
                    self._failed = True
                    self._active_backend = "lexical"
                    return None
            return self._model
        self._active_backend = "lexical"
        return None

    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        if not documents:
            return []
        n = max(1, top_n)
        model = self._get_model()
        if model is None:
            logger.info("reranker_using_lexical", top_n=n)
            out = self._fallback.rerank(query, documents, top_n=n)
            return out

        pairs = [[query, doc.page_content or ""] for doc in documents]
        scores = model.predict(pairs)
        ranked = sorted(
            zip(documents, scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        out: list[Document] = []
        for rank, (doc, score) in enumerate(ranked[:n], start=1):
            meta = dict(doc.metadata or {})
            meta["rerank_score"] = float(score)
            meta["rerank_rank"] = rank
            meta["reranker"] = "cross_encoder"
            out.append(Document(page_content=doc.page_content, metadata=meta))
        return out
