from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    doc_id: str
    page: int | None = None
    source: str | None = None
    snippet: str = ""


class ChatAnswer(BaseModel):
    final_answer: str
    reasoning_summary: str = ""
    relevant_pages: list[int] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    routed_doc_ids: list[str] = Field(default_factory=list)
    route_reason: str = ""


class SourceItem(BaseModel):
    """Phase4 product-facing citation source."""

    filename: str | None = None
    doc_id: str | None = None
    page: int | None = None
    snippet: str = ""
    score: float | None = None


class TraceDocItem(BaseModel):
    """Public document snippet for Answer Trace (no prompts/secrets)."""

    filename: str | None = None
    doc_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    score: float | None = None
    retrieval_score: float | None = None
    rerank_score: float | None = None
    chunk_confidence: float | None = None
    chunk_confidence_percent: int | None = None
    confidence_formula: str | None = None
    rank: int | None = None
    snippet: str = ""


class ConfidenceInfo(BaseModel):
    score: float = 0.0
    percent: int = 0
    level: str = "Low"
    factors: dict[str, Any] = Field(default_factory=dict)


class AnswerTrace(BaseModel):
    """Explainable RAG pipeline snapshot for UI Trace Panel."""

    route: str = ""
    query_type: str = ""
    route_method: str = ""
    mode: str = ""
    original_query: str = ""
    rewritten_query: str = ""
    rewrite_method: str = ""
    used_rewrite: bool = False
    use_hybrid: bool = False
    retrieval: dict[str, Any] = Field(default_factory=dict)
    reranking: dict[str, Any] = Field(default_factory=dict)
    generation: dict[str, Any] = Field(default_factory=dict)
    confidence: ConfidenceInfo = Field(default_factory=ConfidenceInfo)
    retrieved_docs: list[TraceDocItem] = Field(default_factory=list)
    reranked_docs: list[TraceDocItem] = Field(default_factory=list)
    model: str = ""
    confidence_percent: int = 0
    confidence_level: str = ""


class ProductChatResponse(BaseModel):
    """Phase4 chat contract: answer + sources (+ Answer Trace)."""

    answer: str
    sources: list[SourceItem] = Field(default_factory=list)
    query_type: str = ""
    mode: str = ""
    route_method: str = ""
    # Answer Trace (Phase4 Enhancement Step1)
    confidence: str | int | float = ""
    confidence_percent: int = 0
    confidence_level: str = ""
    route: str = ""
    retrieved_docs: list[TraceDocItem] = Field(default_factory=list)
    reranked_docs: list[TraceDocItem] = Field(default_factory=list)
    model: str = ""
    trace: AnswerTrace | None = None
    # Backward-compatible mirrors for existing Gradio clients
    final_answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_summary: str = ""
    route_reason: str = ""
    relevant_pages: list[int] = Field(default_factory=list)
    routed_doc_ids: list[str] = Field(default_factory=list)
    # Step3 Conversation Memory
    conversation_id: str = ""
    memory: dict[str, Any] = Field(default_factory=dict)
    # Step3.5 Query Rewrite / Hybrid (also mirrored inside trace)
    original_query: str = ""
    rewritten_query: str = ""
    rewrite_method: str = ""
    use_hybrid: bool = False
