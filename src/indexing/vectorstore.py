from __future__ import annotations

from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config.settings import Settings, get_settings
from src.indexing.embeddings import get_embeddings


class VectorStoreManager:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._store: Chroma | None = None

    @property
    def store(self) -> Chroma:
        if self._store is None:
            self._store = Chroma(
                collection_name=self.settings.collection_name,
                persist_directory=self.settings.vector_db_path,
                embedding_function=get_embeddings(
                    base_url=self.settings.ollama_base_url,
                    model=self.settings.embed_model,
                ),
                # 默认用的是 cosine 距离，显式指定使用 L2 距离
                # collection_metadata={"hnsw:space": "l2"},
            )
        return self._store

    def refresh(self) -> None:
        self._store = None

    def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> list[str]:
        return self.store.add_documents(documents, ids=ids)

    def delete_by_doc_id(self, doc_id: str) -> int:
        collection = self.store._collection
        existing = collection.get(where={"doc_id": doc_id})
        ids = existing.get("ids") or []
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def reset(self) -> None:
        try:
            self.store.delete_collection()
        except Exception:
            pass
        self.refresh()

    def similarity_search(
        self,
        query: str,
        k: int,
        doc_ids: list[str] | None = None,
    ) -> list[Document]:
        filt: dict[str, Any] | None = None
        if doc_ids:
            if len(doc_ids) == 1:
                filt = {"doc_id": doc_ids[0]}
            else:
                filt = {"doc_id": {"$in": doc_ids}}
        return self.store.similarity_search(query, k=k, filter=filt)

    def similarity_search_with_score(
        self,
        query: str,
        k: int,
        doc_ids: list[str] | None = None,
    ) -> list[tuple[Document, float]]:
        """Dense recall with distance scores (lower distance = closer)."""
        filt: dict[str, Any] | None = None
        if doc_ids:
            if len(doc_ids) == 1:
                filt = {"doc_id": doc_ids[0]}
            else:
                filt = {"doc_id": {"$in": doc_ids}}
        return self.store.similarity_search_with_score(query, k=k, filter=filt)

    def get_all_by_doc_id(self, doc_id: str) -> list[Document]:
        raw = self.store._collection.get(where={"doc_id": doc_id}, include=["documents", "metadatas"])
        docs: list[Document] = []
        for text, meta in zip(raw.get("documents") or [], raw.get("metadatas") or []):
            docs.append(Document(page_content=text or "", metadata=meta or {}))
        return docs

    def count(self) -> int:
        return int(self.store._collection.count())
