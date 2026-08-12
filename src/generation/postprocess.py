from __future__ import annotations

import json
import re
from typing import Any

from json_repair import repair_json
from langchain_core.documents import Document

from src.generation.schemas import ChatAnswer, Citation


def docs_to_citations(documents: list[Document], snippet_len: int = 200) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[tuple[str, int | None]] = set()
    for doc in documents:
        meta = doc.metadata or {}
        doc_id = str(meta.get("doc_id") or "unknown")
        page = _safe_int(meta.get("page"))
        key = (doc_id, page)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            Citation(
                doc_id=doc_id,
                page=page,
                source=str(meta.get("source") or meta.get("filename") or ""),
                snippet=(doc.page_content or "")[:snippet_len],
            )
        )
    return citations


def validate_page_references(
    pages: list[int],
    retrieval_docs: list[Document],
    min_pages: int = 1,
) -> list[int]:
    allowed = []
    for doc in retrieval_docs:
        p = _safe_int((doc.metadata or {}).get("page"))
        if p is not None:
            allowed.append(p)
    allowed_set = set(allowed)
    validated = [p for p in pages if p in allowed_set]
    if len(validated) < min_pages:
        for p in allowed:
            if p not in validated:
                validated.append(p)
            if len(validated) >= min_pages:
                break
    # preserve order, unique
    out: list[int] = []
    for p in validated:
        if p not in out:
            out.append(p)
    return out


def parse_llm_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    repaired = repair_json(text)
    data = json.loads(repaired)
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    return data


def build_chat_answer(
    raw_llm: str,
    retrieval_docs: list[Document],
    routed_doc_ids: list[str],
    route_reason: str,
) -> ChatAnswer:
    citations = docs_to_citations(retrieval_docs)
    try:
        data = parse_llm_json(raw_llm)
        final_answer = str(data.get("final_answer") or "").strip()
        reasoning = str(data.get("reasoning_summary") or "").strip()
        pages_raw = data.get("relevant_pages") or []
        pages = [_safe_int(p) for p in pages_raw]
        pages = [p for p in pages if p is not None]
    except Exception:
        final_answer = (raw_llm or "").strip()
        reasoning = "模型未返回合法 JSON，已回退为纯文本答案。"
        pages = []

    if not final_answer:
        final_answer = "文档中未找到相关内容。"

    validated_pages = validate_page_references(pages, retrieval_docs, min_pages=1 if retrieval_docs else 0)
    return ChatAnswer(
        final_answer=final_answer,
        reasoning_summary=reasoning,
        relevant_pages=validated_pages,
        citations=citations,
        routed_doc_ids=routed_doc_ids,
        route_reason=route_reason,
    )


def _safe_int(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
