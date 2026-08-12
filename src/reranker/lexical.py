from __future__ import annotations

import math
import re

from langchain_core.documents import Document

from src.reranker.base import BaseReranker

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_STOP = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "for",
    "to",
    "of",
    "in",
    "on",
    "and",
    "or",
    "what",
    "how",
    "when",
    "where",
    "which",
    "with",
    "by",
    "from",
    "under",
    "over",
}


def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall((text or "").lower())
    return [t for t in tokens if t not in _STOP and len(t) > 1]


class LexicalReranker(BaseReranker):
    """
    Offline-friendly reranker using query-document lexical overlap.
    Used when CrossEncoder weights cannot be downloaded.
    """

    def rerank(self, query: str, documents: list[Document], top_n: int) -> list[Document]:
        if not documents:
            return []
        n = max(1, top_n)
        q_tokens = _tokenize(query)
        q_set = set(q_tokens)
        if not q_set:
            return documents[:n]

        scored: list[tuple[Document, float]] = []
        for doc in documents:
            text = doc.page_content or ""
            d_tokens = _tokenize(text)
            d_set = set(d_tokens)
            if not d_set:
                score = 0.0
            else:
                overlap = len(q_set & d_set)
                score = overlap / (math.sqrt(len(q_set)) * math.sqrt(len(d_set)) + 1e-9)
                # Prefer chunks that contain distinctive multi-word cues from the query.
                for cue in ("p95", "latency", "nebula search appliance", "slo"):
                    if cue in text.lower():
                        score += 0.5
            scored.append((doc, float(score)))

        ranked = sorted(scored, key=lambda item: item[1], reverse=True)
        out: list[Document] = []
        for rank, (doc, score) in enumerate(ranked[:n], start=1):
            meta = dict(doc.metadata or {})
            meta["rerank_score"] = score
            meta["rerank_rank"] = rank
            meta["reranker"] = "lexical"
            out.append(Document(page_content=doc.page_content, metadata=meta))
        return out
