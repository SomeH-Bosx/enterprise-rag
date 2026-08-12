from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RouteDecision:
    doc_ids: list[str] = field(default_factory=list)
    schema: str = "string"
    matched_filenames: list[str] = field(default_factory=list)
    reason: str = "global"


def route_query(question: str, documents: list[dict[str, Any]]) -> RouteDecision:
    """Rule-based router: shrink search space when question mentions a filename/doc stem."""
    q = (question or "").strip().lower()
    if not q or not documents:
        return RouteDecision(doc_ids=[], reason="global_empty")

    matched: list[dict[str, Any]] = []
    for doc in documents:
        filename = str(doc.get("filename") or "")
        stem = filename.rsplit(".", 1)[0].lower() if filename else ""
        doc_id = str(doc.get("doc_id") or "")
        aliases = {filename.lower(), stem, doc_id.lower()}
        aliases = {a for a in aliases if a}
        if any(alias and alias in q for alias in aliases):
            matched.append(doc)

    if matched:
        return RouteDecision(
            doc_ids=[str(d["doc_id"]) for d in matched],
            matched_filenames=[str(d.get("filename")) for d in matched],
            reason="filename_match",
            schema="string",
        )
    return RouteDecision(doc_ids=[], reason="global", schema="string")
