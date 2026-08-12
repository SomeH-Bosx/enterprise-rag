from __future__ import annotations

from langchain_core.documents import Document

from src.indexing.vectorstore import VectorStoreManager


def apply_pdr(documents: list[Document], vector_store: VectorStoreManager) -> list[Document]:
    """Expand chunks to page-level parents when page metadata is reliable."""
    if not documents:
        return []

    expanded: list[Document] = []
    seen_pages: set[tuple[str, int]] = set()

    for doc in documents:
        meta = doc.metadata or {}
        doc_id = str(meta.get("doc_id") or "")
        page = meta.get("page")
        if page is None or page == "":
            expanded.append(doc)
            continue
        try:
            page_i = int(page)
        except (TypeError, ValueError):
            expanded.append(doc)
            continue

        key = (doc_id, page_i)
        if key in seen_pages:
            continue
        seen_pages.add(key)

        siblings = vector_store.get_all_by_doc_id(doc_id)
        same_page = [
            s for s in siblings if _safe_page(s.metadata.get("page")) == page_i
        ]
        if not same_page:
            expanded.append(doc)
            continue

        same_page_sorted = sorted(
            same_page,
            key=lambda d: str(d.metadata.get("chunk_id") or ""),
        )
        merged = "\n\n".join(s.page_content for s in same_page_sorted)
        expanded.append(
            Document(
                page_content=merged,
                metadata={
                    **meta,
                    "page": page_i,
                    "pdr": True,
                    "chunk_id": f"{doc_id}:page:{page_i}",
                },
            )
        )
    return expanded


def _safe_page(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
