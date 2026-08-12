from __future__ import annotations

from http import HTTPStatus
from typing import Any

from langchain_core.documents import Document

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.reranker.base import BaseReranker
from src.reranker.lexical import LexicalReranker

logger = get_logger("dashscope_reranker")


class DashScopeRerankError(RuntimeError):
    """Raised when DashScope rerank API cannot produce a valid ranking."""


class DashScopeReranker(BaseReranker):
    """
    Semantic reranker via DashScope TextReRank API.
    Falls back to LexicalReranker when API key missing or call fails.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        api_key: str | None = None,
        model: str | None = None,
        enable_fallback: bool = True,
    ):
        self.settings = settings or get_settings()
        self.api_key = (api_key if api_key is not None else self.settings.dashscope_api_key) or ""
        self.model = model or self.settings.dashscope_rerank_model
        self.enable_fallback = enable_fallback
        self._fallback = LexicalReranker()

    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        if not documents:
            return []
        n = max(1, top_n)

        if not self.api_key.strip():
            logger.warning("dashscope_api_key_missing_fallback_lexical")
            if self.enable_fallback:
                return self._fallback_rerank(query, documents, n)
            raise DashScopeRerankError("DASHSCOPE_API_KEY is empty")

        try:
            ranked = self._call_dashscope(query, documents, n)
            return ranked
        except Exception as exc:  # noqa: BLE001
            logger.warning("dashscope_rerank_failed_fallback_lexical", error=str(exc))
            if self.enable_fallback:
                return self._fallback_rerank(query, documents, n)
            raise

    def _fallback_rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        out = self._fallback.rerank(query, documents, top_n=top_n)
        for doc in out:
            meta = dict(doc.metadata or {})
            meta["reranker"] = "lexical_fallback"
            doc.metadata = meta
        return out

    def _call_dashscope(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        import dashscope
        from dashscope import TextReRank

        dashscope.api_key = self.api_key
        texts = [d.page_content or "" for d in documents]

        logger.info(
            "dashscope_rerank_call",
            model=self.model,
            candidates=len(texts),
            top_n=top_n,
        )
        resp = TextReRank.call(
            model=self.model,
            query=query,
            documents=texts,
            top_n=top_n,
            return_documents=False,
        )

        status = getattr(resp, "status_code", None)
        if status is not None and status != HTTPStatus.OK:
            message = getattr(resp, "message", None) or getattr(resp, "code", None) or str(resp)
            raise DashScopeRerankError(f"DashScope rerank failed: status={status}, message={message}")

        results = self._extract_results(resp)
        if not results:
            raise DashScopeRerankError("DashScope rerank returned empty results")

        out: list[Document] = []
        for rank, item in enumerate(results[:top_n], start=1):
            idx = int(item["index"])
            if idx < 0 or idx >= len(documents):
                continue
            src = documents[idx]
            meta = dict(src.metadata or {})
            meta["rerank_score"] = float(item.get("relevance_score", 0.0))
            meta["rerank_rank"] = rank
            meta["reranker"] = "dashscope"
            meta["rerank_model"] = self.model
            out.append(Document(page_content=src.page_content, metadata=meta))

        if not out:
            raise DashScopeRerankError("DashScope rerank produced no mappable documents")
        return out

    @staticmethod
    def _extract_results(resp: Any) -> list[dict[str, Any]]:
        """Normalize SDK response shapes into [{index, relevance_score}, ...]."""
        output = getattr(resp, "output", None)
        raw = None
        if output is not None:
            if isinstance(output, dict):
                raw = output.get("results")
            else:
                raw = getattr(output, "results", None)
        if raw is None and isinstance(resp, dict):
            raw = (resp.get("output") or {}).get("results")

        if not raw:
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "index": int(item.get("index")),
                        "relevance_score": float(item.get("relevance_score", 0.0)),
                    }
                )
            else:
                normalized.append(
                    {
                        "index": int(getattr(item, "index")),
                        "relevance_score": float(getattr(item, "relevance_score", 0.0)),
                    }
                )
        # API usually returns sorted results; keep stable descending sort.
        normalized.sort(key=lambda x: x["relevance_score"], reverse=True)
        return normalized
