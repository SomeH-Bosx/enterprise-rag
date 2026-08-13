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


def aggregate_recall(hits: Iterable[bool]) -> dict[str, Any]:
    rows = list(hits)
    n = len(rows)
    scored = sum(1 for h in rows if h)
    return {
        "total": n,
        "hits": scored,
        "recall_at_k": (scored / n) if n else 0.0,
    }
