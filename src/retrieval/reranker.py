"""Compatibility shim. Phase 2 implementation lives in `src.reranker`."""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document

from src.reranker import Reranker

# Backward-compatible alias used by older imports / QAService type hints.
CrossEncoderReranker = Reranker


def naive_dense_only(
    query: str,
    vector_store: Any,
    k: int,
    doc_ids: list[str] | None = None,
) -> list[Document]:
    """Thin helper around VectorStoreManager.similarity_search (unchanged core)."""
    return vector_store.similarity_search(query, k=k, doc_ids=doc_ids or None)


def dense_with_scores(
    query: str,
    vector_store: Any,
    k: int,
    doc_ids: list[str] | None = None,
) -> list[Document]:
    """
    Dense recall that attaches retrieval_score (0–1 similarity-like) on metadata.
    Falls back to plain similarity_search if with_score is unavailable.
    """
    from src.generation.trace import distance_to_similarity

    ids = doc_ids or None
    search_scored = getattr(vector_store, "similarity_search_with_score", None)
    if callable(search_scored):
        pairs = search_scored(query, k=k, doc_ids=ids)
        docs: list[Document] = []
        for doc, distance in pairs:
            meta = dict(doc.metadata or {})
            sim = distance_to_similarity(distance)
            if sim is not None:
                meta["retrieval_score"] = round(sim, 6)
                meta["retrieval_distance"] = float(distance)
            docs.append(Document(page_content=doc.page_content, metadata=meta))
        return docs
    return vector_store.similarity_search(query, k=k, doc_ids=ids)
