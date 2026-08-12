from __future__ import annotations

from langchain_core.documents import Document

from src.config.settings import Settings, get_settings
from src.generation.trace import distance_to_similarity
from src.indexing.bm25_store import BM25Store
from src.indexing.vectorstore import VectorStoreManager


def _chunk_key(doc: Document) -> str:
    chunk_id = doc.metadata.get("chunk_id")
    if chunk_id:
        return str(chunk_id)
    return f"{doc.metadata.get('doc_id')}::{doc.metadata.get('page')}::{hash(doc.page_content)}"


def rrf_fuse(
    ranked_lists: list[list[Document]],
    k: int = 60,
) -> list[Document]:
    scores: dict[str, float] = {}
    keep: dict[str, Document] = {}
    for docs in ranked_lists:
        for rank, doc in enumerate(docs, start=1):
            key = _chunk_key(doc)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in keep:
                keep[key] = Document(
                    page_content=doc.page_content,
                    metadata=dict(doc.metadata or {}),
                )
            else:
                # preserve richer metadata (e.g. dense retrieval_score)
                keep[key].metadata.update(
                    {
                        kk: vv
                        for kk, vv in (doc.metadata or {}).items()
                        if kk not in keep[key].metadata or keep[key].metadata.get(kk) is None
                    }
                )
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    fused: list[Document] = []
    for key, score in ordered:
        doc = keep[key]
        meta = dict(doc.metadata or {})
        meta["rrf_score"] = score
        # Ensure retrieval_score for Trace/Confidence when only BM25 hit
        if meta.get("retrieval_score") is None:
            # RRF ~ 1/(60+rank); map roughly into (0,1)
            meta["retrieval_score"] = round(min(1.0, float(score) * 30.0), 6)
        fused.append(Document(page_content=doc.page_content, metadata=meta))
    return fused


def _dense_with_scores(
    query: str,
    vector_store: VectorStoreManager,
    k: int,
    doc_ids: list[str] | None,
) -> list[Document]:
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


def hybrid_retrieve(
    query: str,
    vector_store: VectorStoreManager,
    bm25_store: BM25Store,
    doc_ids: list[str] | None = None,
    settings: Settings | None = None,
    use_bm25: bool | None = None,
    recall_top_n: int | None = None,
) -> list[Document]:
    """
    Dense (+ optional BM25) recall with RRF fusion.

    When use_bm25 is False, returns dense-only scored candidates (no BM25).
    """
    cfg = settings or get_settings()
    n = recall_top_n if recall_top_n is not None else cfg.recall_top_n
    enable_bm25 = cfg.use_bm25 if use_bm25 is None else use_bm25

    dense_docs = _dense_with_scores(query, vector_store, n, doc_ids)
    if not enable_bm25:
        return dense_docs

    sparse_docs = bm25_store.search(query, k=n, doc_ids=doc_ids or None)
    if not sparse_docs:
        return dense_docs
    return rrf_fuse([dense_docs, sparse_docs])
