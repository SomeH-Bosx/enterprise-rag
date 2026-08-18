from __future__ import annotations

from langchain_core.documents import Document

from src.config.settings import Settings, get_settings
from src.generation.trace import distance_to_similarity
from src.indexing.bm25_store import BM25Store
from src.indexing.vectorstore import VectorStoreManager

ALLOWED_RETRIEVAL_MODES = frozenset({"dense", "bm25", "hybrid"})


def normalize_retrieval_mode(
    value: str | None,
    *,
    use_bm25_fallback: bool = False,
) -> str:
    mode = (value or "").strip().lower()
    if mode in ALLOWED_RETRIEVAL_MODES:
        return mode
    return "hybrid" if use_bm25_fallback else "dense"


def resolve_retrieval_mode(settings: Settings | None = None) -> str:
    """Prefer RETRIEVAL_MODE; empty/invalid falls back to USE_BM25 → hybrid else dense."""
    cfg = settings or get_settings()
    return normalize_retrieval_mode(
        getattr(cfg, "retrieval_mode", None),
        use_bm25_fallback=bool(cfg.use_bm25),
    )


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


def _bm25_with_scores(
    query: str,
    bm25_store: BM25Store,
    k: int,
    doc_ids: list[str] | None,
) -> list[Document]:
    sparse_docs = bm25_store.search(query, k=k, doc_ids=doc_ids or None)
    if not sparse_docs:
        return []
    raw_scores: list[float] = []
    for doc in sparse_docs:
        try:
            raw_scores.append(float((doc.metadata or {}).get("bm25_score") or 0.0))
        except (TypeError, ValueError):
            raw_scores.append(0.0)
    peak = max(raw_scores) if raw_scores else 0.0
    out: list[Document] = []
    for doc, raw in zip(sparse_docs, raw_scores):
        meta = dict(doc.metadata or {})
        if peak > 0:
            meta["retrieval_score"] = round(min(1.0, raw / peak), 6)
        else:
            meta["retrieval_score"] = 0.0
        meta["retrieval_backend"] = "bm25"
        out.append(Document(page_content=doc.page_content, metadata=meta))
    return out


def hybrid_retrieve(
    query: str,
    vector_store: VectorStoreManager,
    bm25_store: BM25Store,
    doc_ids: list[str] | None = None,
    settings: Settings | None = None,
    use_bm25: bool | None = None,
    retrieval_mode: str | None = None,
    recall_top_n: int | None = None,
) -> list[Document]:
    """
    Recall by mode: dense | bm25 | hybrid (Dense+BM25 RRF).

    Legacy: if retrieval_mode is omitted, use_bm25 True → hybrid else dense
    (or settings.retrieval_mode / USE_BM25 via resolve_retrieval_mode).
    """
    cfg = settings or get_settings()
    n = recall_top_n if recall_top_n is not None else cfg.recall_top_n

    if retrieval_mode is not None:
        mode = normalize_retrieval_mode(retrieval_mode, use_bm25_fallback=False)
    elif use_bm25 is not None:
        mode = "hybrid" if use_bm25 else "dense"
    else:
        mode = resolve_retrieval_mode(cfg)

    if mode == "bm25":
        return _bm25_with_scores(query, bm25_store, n, doc_ids)[:n]

    dense_docs = _dense_with_scores(query, vector_store, n, doc_ids)
    if mode == "dense":
        return dense_docs[:n]

    sparse_docs = bm25_store.search(query, k=n, doc_ids=doc_ids or None)
    if not sparse_docs:
        return dense_docs[:n]
    # RRF formula unchanged; cap fused list so candidate_count cannot exceed n.
    return rrf_fuse([dense_docs, sparse_docs])[:n]
