"""Phase5 评测用的 Recall@K 辅助函数。"""

from __future__ import annotations

from typing import Any, Iterable, Sequence


def filename_hit(retrieved_files: Sequence[str], expected_filename: str | None) -> bool:
    if not expected_filename:
        return False
    needle = expected_filename.lower().strip()
    return any(needle in (f or "").lower() for f in retrieved_files)


def doc_id_hit(retrieved_doc_ids: Sequence[str], expected_doc_id: str | None) -> bool:
    if not expected_doc_id:
        return False
    return str(expected_doc_id) in {str(x) for x in retrieved_doc_ids}


def recall_hit(
    *,
    retrieved_files: Sequence[str],
    retrieved_doc_ids: Sequence[str],
    expected_filename: str | None = None,
    expected_doc_id: str | None = None,
) -> bool:
    return doc_id_hit(retrieved_doc_ids, expected_doc_id) or filename_hit(
        retrieved_files, expected_filename
    )


def citation_pairs(
    retrieved_files: Sequence[str],
    retrieved_pages: Sequence[Any],
) -> list[tuple[str, int]]:
    files = list(retrieved_files or [])
    pages = list(retrieved_pages or [])
    n = min(len(files), len(pages))
    pairs: list[tuple[str, int]] = []
    for i in range(n):
        try:
            pairs.append((str(files[i] or ""), int(pages[i])))
        except (TypeError, ValueError):
            continue
    return pairs


def strict_citation_hit(
    *,
    retrieved_files: Sequence[str],
    retrieved_pages: Sequence[Any],
    expected_filename: str | None,
    expected_page: Any,
) -> bool | None:
    """True iff some retrieved (filename, page) matches expected filename+page.

    Filename rule matches ``filename_hit`` (case-insensitive substring).
    Returns None when the question has no page label (excluded from the rate).
    """
    if expected_page is None:
        return None
    if not expected_filename:
        return False
    try:
        want = int(expected_page)
    except (TypeError, ValueError):
        return False
    needle = expected_filename.lower().strip()
    for filename, page in citation_pairs(retrieved_files, retrieved_pages):
        if needle in filename.lower() and page == want:
            return True
    return False


def aggregate_recall(hits: Iterable[bool]) -> dict[str, Any]:
    rows = list(hits)
    n = len(rows)
    scored = sum(1 for h in rows if h)
    return {
        "total": n,
        "hits": scored,
        "recall_at_k": (scored / n) if n else 0.0,
    }
