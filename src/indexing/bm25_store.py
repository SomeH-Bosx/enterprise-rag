from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from src.config.settings import Settings, get_settings

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Store:
    """Persistent BM25 corpus keyed by chunk_id."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.path = Path(self.settings.bm25_store_path)
        self._records: dict[str, dict[str, Any]] = {}
        self._bm25: BM25Okapi | None = None
        self._id_order: list[str] = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._records = data.get("records", {})
        else:
            self._records = {}
        self._rebuild_index()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": self._records}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _rebuild_index(self) -> None:
        self._id_order = list(self._records.keys())
        if not self._id_order:
            self._bm25 = None
            return
        corpus = [tokenize(self._records[cid]["text"]) for cid in self._id_order]
        self._bm25 = BM25Okapi(corpus)

    def upsert_documents(self, documents: list[Document]) -> None:
        for doc in documents:
            chunk_id = str(doc.metadata.get("chunk_id"))
            if not chunk_id or chunk_id == "None":
                continue
            self._records[chunk_id] = {
                "text": doc.page_content,
                "metadata": dict(doc.metadata),
            }
        self._rebuild_index()
        self.save()

    def delete_by_doc_id(self, doc_id: str) -> int:
        to_delete = [
            cid
            for cid, rec in self._records.items()
            if str(rec.get("metadata", {}).get("doc_id")) == doc_id
        ]
        for cid in to_delete:
            del self._records[cid]
        if to_delete:
            self._rebuild_index()
            self.save()
        return len(to_delete)

    def reset(self) -> None:
        self._records = {}
        self._bm25 = None
        self._id_order = []
        if self.path.exists():
            self.path.unlink()

    def search(
        self,
        query: str,
        k: int,
        doc_ids: list[str] | None = None,
    ) -> list[Document]:
        if not self._bm25 or not self._id_order:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores = self._bm25.get_scores(q_tokens)
        # Tiny corpora often yield all-zero BM25 IDF scores; fall back to overlap.
        if max(float(s) for s in scores) <= 0.0:
            scores = []
            q_set = set(q_tokens)
            for cid in self._id_order:
                text = str(self._records[cid].get("text") or "")
                overlap = len(q_set.intersection(tokenize(text)))
                scores.append(float(overlap))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results: list[Document] = []
        for idx in ranked:
            cid = self._id_order[idx]
            rec = self._records[cid]
            meta = dict(rec.get("metadata") or {})
            if doc_ids and str(meta.get("doc_id")) not in doc_ids:
                continue
            if scores[idx] <= 0:
                continue
            results.append(
                Document(
                    page_content=rec["text"],
                    metadata={**meta, "bm25_score": float(scores[idx])},
                )
            )
            if len(results) >= k:
                break
        return results

    def count(self) -> int:
        return len(self._records)
