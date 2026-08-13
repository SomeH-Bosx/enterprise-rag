"""Answer Trace + Confidence：可解释 RAG 响应辅助。"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document


def distance_to_similarity(distance: float | None) -> float | None:
    """将 Chroma distance（越小越好）转为 0–1 相似度风格分数。"""
    if distance is None:
        return None
    try:
        d = max(0.0, float(distance))
    except (TypeError, ValueError):
        return None
    return 1.0 / (1.0 + d)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _calibrate_retrieval_sim(raw: float) -> float:
    """
    Chroma 1/(1+d) often clusters mid-band; mild lift so strong hits feel higher.
    raw^0.65 maps ~0.55→~0.68, ~0.70→~0.80 while keeping order.
    """
    return _clamp(float(raw) ** 0.65)


def compute_chunk_confidence(
    retrieval_score: float | None,
    rerank_score: float | None,
) -> dict[str, Any]:
    """
    Per-chunk confidence for Trace Panel.

    If both scores: 0.4 * retrieval + 0.6 * rerank
    Else: whichever is available.
    """
    r = float(retrieval_score) if retrieval_score is not None else None
    rr = float(rerank_score) if rerank_score is not None else None
    if r is not None:
        r = _clamp(r)
    if rr is not None:
        rr = _clamp(rr)

    if r is not None and rr is not None:
        conf = _clamp(0.4 * r + 0.6 * rr)
        formula = f"0.4×{r:.3f}(retrieval) + 0.6×{rr:.3f}(rerank) = {conf:.3f}"
    elif rr is not None:
        conf = rr
        formula = f"rerank_only = {rr:.3f}"
    elif r is not None:
        conf = r
        formula = f"retrieval_only = {r:.3f}"
    else:
        return {
            "chunk_confidence": None,
            "retrieval_score": None,
            "rerank_score": None,
            "formula": "n/a (no scores)",
            "percent": None,
        }

    return {
        "chunk_confidence": round(conf, 4),
        "retrieval_score": round(r, 4) if r is not None else None,
        "rerank_score": round(rr, 4) if rr is not None else None,
        "formula": formula,
        "percent": int(round(conf * 100)),
    }


def doc_to_trace_item(doc: Document, *, rank: int | None = None) -> dict[str, Any]:
    meta = doc.metadata or {}
    retrieval_score = meta.get("retrieval_score")
    rerank_score = meta.get("rerank_score")
    try:
        retrieval_score = float(retrieval_score) if retrieval_score is not None else None
    except (TypeError, ValueError):
        retrieval_score = None
    try:
        rerank_score = float(rerank_score) if rerank_score is not None else None
    except (TypeError, ValueError):
        rerank_score = None

    chunk_conf = compute_chunk_confidence(retrieval_score, rerank_score)
    display_score = chunk_conf.get("chunk_confidence")
    if display_score is None:
        display_score = rerank_score if rerank_score is not None else retrieval_score

    return {
        "filename": meta.get("filename") or meta.get("source") or "",
        "doc_id": meta.get("doc_id"),
        "page": meta.get("page"),
        "chunk_id": meta.get("chunk_id"),
        "score": float(display_score) if display_score is not None else None,
        "retrieval_score": chunk_conf.get("retrieval_score"),
        "rerank_score": chunk_conf.get("rerank_score"),
        "chunk_confidence": chunk_conf.get("chunk_confidence"),
        "chunk_confidence_percent": chunk_conf.get("percent"),
        "confidence_formula": chunk_conf.get("formula"),
        "rank": rank if rank is not None else meta.get("rerank_rank"),
        "snippet": (doc.page_content or "")[:160],
    }


def unique_filenames(docs: list[Document], limit: int = 12) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for d in docs:
        meta = d.metadata or {}
        name = str(meta.get("filename") or meta.get("source") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


_REFUSAL_MARKERS = (
    "未找到",
    "找不到",
    "不知道",
    "无法回答",
    "没有相关",
    "文档中没有",
    "no relevant",
    "cannot find",
    "don't know",
    "do not know",
)


def _top_heavy_mean(values: list[float], *, top_n: int = 3) -> float:
    """Emphasize best hit: 70% top-1 + 30% mean of top-N."""
    if not values:
        return 0.0
    ordered = sorted((float(v) for v in values), reverse=True)
    top1 = ordered[0]
    head = ordered[:top_n]
    return 0.70 * top1 + 0.30 * _mean(head)


def compute_confidence(
    *,
    query_type: str,
    retrieved: bool,
    answer: str,
    retrieval_scores: list[float] | None = None,
    rerank_scores: list[float] | None = None,
    source_count: int = 0,
    expected_sources: int = 1,
) -> dict[str, Any]:
    """
    Answer-level confidence calibrated for demo intuition.

    Weights (knowledge path):
      calibrated retrieval 25% · top-heavy rerank 50% · source 10% · grounding 15%

    Levels: High ≥65 · Medium ≥45 · else Low
    """
    text = (answer or "").strip()
    ret_scores = [float(s) for s in (retrieval_scores or []) if s is not None]
    rr_scores = [_clamp(float(s)) for s in (rerank_scores or []) if s is not None]

    if query_type == "casual_chat" or not retrieved:
        score = 0.58
        factors = {
            "retrieval": None,
            "rerank": None,
            "source_coverage": None,
            "grounding": round(score, 4),
            "note": "casual_chat_or_no_retrieval",
            "formula": "casual_chat fixed ≈ 0.58 (no retrieval evidence)",
        }
        return _pack_confidence(score, factors)

    retrieval_raw = _top_heavy_mean(ret_scores) if ret_scores else 0.0
    retrieval_cal = _calibrate_retrieval_sim(retrieval_raw) if ret_scores else 0.0

    if rr_scores:
        rerank_signal = _top_heavy_mean(rr_scores)
    else:
        rerank_signal = retrieval_cal

    denom = max(1, expected_sources)
    source_coverage = _clamp(source_count / float(denom))

    lowered = text.lower()
    is_refusal = any(m in text or m in lowered for m in _REFUSAL_MARKERS)
    if is_refusal:
        grounding = 0.18
    elif source_count > 0 and len(text) >= 40:
        grounding = 0.92
    elif source_count > 0 and len(text) >= 15:
        grounding = 0.75
    elif source_count > 0:
        grounding = 0.55
    else:
        grounding = 0.22

    w_ret, w_rr, w_src, w_g = 0.25, 0.50, 0.10, 0.15
    score = (
        w_ret * _clamp(retrieval_cal)
        + w_rr * _clamp(rerank_signal)
        + w_src * source_coverage
        + w_g * grounding
    )
    score = _clamp(score)
    formula = (
        f"{w_ret}×{retrieval_cal:.3f}(retrieval_cal) + "
        f"{w_rr}×{rerank_signal:.3f}(rerank) + "
        f"{w_src}×{source_coverage:.3f}(source) + "
        f"{w_g}×{grounding:.3f}(grounding) = {score:.3f}"
    )
    factors = {
        "retrieval_raw": round(retrieval_raw, 4),
        "retrieval": round(retrieval_cal, 4),
        "rerank": round(rerank_signal, 4),
        "source_coverage": round(source_coverage, 4),
        "grounding": round(grounding, 4),
        "weights": {
            "retrieval": w_ret,
            "rerank": w_rr,
            "source": w_src,
            "grounding": w_g,
        },
        "formula": formula,
        "calibration": "retrieval = top_heavy(sim)^0.65; rerank = 0.7*top1 + 0.3*mean(top3)",
    }
    return _pack_confidence(score, factors)


def _pack_confidence(score: float, factors: dict[str, Any]) -> dict[str, Any]:
    percent = int(round(score * 100))
    # Calibrated thresholds (more intuitive for demo): High≥65, Medium≥45
    if percent >= 65:
        level = "High"
    elif percent >= 45:
        level = "Medium"
    else:
        level = "Low"
    return {
        "score": round(score, 4),
        "percent": percent,
        "level": level,
        "factors": factors,
    }


def build_answer_trace(
    *,
    query_type: str,
    route_method: str,
    mode: str,
    retrieved: bool,
    answer: str,
    candidates: list[Document] | None = None,
    ranked: list[Document] | None = None,
    recall_k: int | None = None,
    top_n: int | None = None,
    use_reranker: bool = False,
    use_hybrid: bool = False,
    original_query: str = "",
    rewritten_query: str = "",
    rewrite_method: str = "",
    used_rewrite: bool = False,
    reranker_backend: str = "",
    llm_model: str = "",
    embed_model: str = "",
    expected_sources: int = 1,
) -> dict[str, Any]:
    """Build public Answer Trace payload (no prompts / secrets)."""
    candidates = candidates or []
    ranked = ranked or []

    retrieval_scores: list[float] = []
    for d in candidates:
        s = (d.metadata or {}).get("retrieval_score")
        if s is not None:
            try:
                retrieval_scores.append(float(s))
            except (TypeError, ValueError):
                pass

    rerank_scores: list[float] = []
    for d in ranked:
        s = (d.metadata or {}).get("rerank_score")
        if s is not None:
            try:
                rerank_scores.append(float(s))
            except (TypeError, ValueError):
                pass

    retrieved_items = [doc_to_trace_item(d, rank=i + 1) for i, d in enumerate(candidates[:20])]
    reranked_items = [doc_to_trace_item(d, rank=i + 1) for i, d in enumerate(ranked[:10])]

    unique_source_count = len(
        {
            str((d.metadata or {}).get("doc_id") or (d.metadata or {}).get("filename") or i)
            for i, d in enumerate(ranked)
        }
    )
    confidence = compute_confidence(
        query_type=query_type,
        retrieved=retrieved,
        answer=answer,
        retrieval_scores=retrieval_scores,
        rerank_scores=rerank_scores,
        source_count=unique_source_count if retrieved else 0,
        expected_sources=expected_sources,
    )

    reranker_label = ""
    if use_reranker and retrieved:
        backend = (reranker_backend or "").strip().lower()
        if backend == "dashscope":
            reranker_label = "DashScope Reranker"
        elif backend == "cross_encoder":
            reranker_label = "CrossEncoder Reranker"
        elif backend == "lexical":
            reranker_label = "Lexical Reranker"
        else:
            reranker_label = f"Reranker ({backend or 'unknown'})"
    elif retrieved:
        reranker_label = "Disabled (dense only)"
    else:
        reranker_label = "Skipped"

    if use_hybrid and retrieved:
        retriever_label = "Hybrid (Dense + BM25 RRF)"
    elif retrieved:
        retriever_label = "Chroma Dense Similarity"
    else:
        retriever_label = "Skipped"

    return {
        "route": query_type,
        "query_type": query_type,
        "route_method": route_method,
        "mode": mode,
        "original_query": original_query,
        "rewritten_query": rewritten_query or original_query,
        "rewrite_method": rewrite_method,
        "used_rewrite": used_rewrite,
        "use_hybrid": bool(use_hybrid and retrieved),
        "retrieval": {
            "retriever": retriever_label,
            "use_hybrid": bool(use_hybrid and retrieved),
            "top_k": recall_k,
            "candidate_count": len(candidates),
            "documents": unique_filenames(candidates),
            "items": retrieved_items,
            "original_query": original_query,
            "rewritten_query": rewritten_query or original_query,
            "rewrite_method": rewrite_method,
            "note": "Chunks may truncate mid-sentence (character splitter); overlap mitigates context loss.",
        },
        "reranking": {
            "reranker": reranker_label,
            "backend": reranker_backend if use_reranker and retrieved else "",
            "selected_top_n": top_n if use_reranker and retrieved else (len(ranked) if retrieved else 0),
            "documents": unique_filenames(ranked),
            "items": reranked_items,
        },
        "generation": {
            "llm": f"Ollama:{llm_model}" if llm_model else "Ollama",
            "status": "Response Generated",
            "embed_model": embed_model,
            "answer_query": original_query,
            "note": "Answer prompt uses original user query (+ memory); retrieval may use rewritten query.",
        },
        "confidence": confidence,
        # Flat fields for product contract convenience
        "retrieved_docs": retrieved_items,
        "reranked_docs": reranked_items,
        "model": f"Ollama:{llm_model}" if llm_model else "Ollama",
        "confidence_percent": confidence["percent"],
        "confidence_level": confidence["level"],
    }
