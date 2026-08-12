from __future__ import annotations

from abc import ABC, abstractmethod

from langchain_core.documents import Document


class BaseReranker(ABC):
    """Rerank candidates after vector recall. Does not own retrieval."""

    @abstractmethod
    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        """Return top_n documents sorted by relevance to query."""
