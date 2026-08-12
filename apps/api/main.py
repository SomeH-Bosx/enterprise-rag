"""Enterprise RAG FastAPI 入口（产品 API）。

提供上传、问答、健康检查、Session 模型配置等 HTTP 边界；业务逻辑在 `src/services`。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.logging import bind_request_id, get_logger, setup_logging
from src.config.session_models import SessionModelOverrides, defaults_from_settings
from src.config.settings import get_settings
from src.generation.llm_gateway import check_ollama_health
from src.generation.schemas import (
    AnswerTrace,
    ChatAnswer,
    ConfidenceInfo,
    ProductChatResponse,
    SourceItem,
    TraceDocItem,
)
from src.ingestion.loaders import SUPPORTED_SUFFIXES, is_supported
from src.services.exceptions import RagError
from src.services.ingest_service import IngestService
from src.services.qa_service import QAService

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger("api")

app = FastAPI(
    title="Enterprise RAG API",
    version="1.1.0",
    description="产品 API：多格式上传、带引用来源的问答、健康检查、Session 模型配置。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ingest_service = IngestService(settings)
qa_service = QAService(
    settings,
    vector_store=ingest_service.vector_store,
    bm25_store=ingest_service.bm25_store,
    registry=ingest_service.registry,
)


class ChatRequest(BaseModel):
    """接受 Phase4 的 `query` 或旧字段 `question`；可选 `conversation_id` 启用 Memory。"""

    query: str | None = Field(default=None, min_length=1)
    question: str | None = Field(default=None, min_length=1)
    structured: bool = False
    conversation_id: str | None = Field(default=None)
    # Step4 session model overrides (no API keys)
    llm_model: str | None = Field(default=None)
    embed_model: str | None = Field(default=None)
    reranker_backend: str | None = Field(default=None)
    session_models: dict[str, Any] | None = Field(default=None)

    @model_validator(mode="after")
    def require_text(self) -> "ChatRequest":
        text = (self.query or self.question or "").strip()
        if not text:
            raise ValueError("Either 'query' or 'question' is required")
        return self

    @property
    def text(self) -> str:
        return (self.query or self.question or "").strip()

    def model_overrides(self) -> SessionModelOverrides:
        nested = self.session_models if isinstance(self.session_models, dict) else {}
        return SessionModelOverrides.from_mapping(
            {
                "llm_model": self.llm_model or nested.get("llm_model"),
                "embed_model": self.embed_model or nested.get("embed_model"),
                "reranker_backend": self.reranker_backend or nested.get("reranker_backend"),
            }
        )


class SessionModelsRequest(BaseModel):
    """Bind session embed (and echo other model choices). Never accepts API keys."""

    llm_model: str | None = None
    embed_model: str | None = None
    reranker_backend: str | None = None


class CompareRequest(BaseModel):
    question: str = Field(..., min_length=1)


def _citations_to_sources(citations: list[Any]) -> list[SourceItem]:
    sources: list[SourceItem] = []
    for c in citations or []:
        if isinstance(c, dict):
            sources.append(
                SourceItem(
                    filename=c.get("source") or c.get("filename"),
                    doc_id=c.get("doc_id"),
                    page=c.get("page"),
                    snippet=str(c.get("snippet") or ""),
                    score=c.get("rerank_score"),
                )
            )
        else:
            sources.append(
                SourceItem(
                    filename=getattr(c, "source", None),
                    doc_id=getattr(c, "doc_id", None),
                    page=getattr(c, "page", None),
                    snippet=str(getattr(c, "snippet", "") or ""),
                )
            )
    return sources


def _to_trace_docs(items: list[Any] | None) -> list[TraceDocItem]:
    out: list[TraceDocItem] = []
    for item in items or []:
        if isinstance(item, TraceDocItem):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        out.append(
            TraceDocItem(
                filename=item.get("filename"),
                doc_id=item.get("doc_id"),
                page=item.get("page"),
                chunk_id=item.get("chunk_id"),
                score=item.get("score"),
                retrieval_score=item.get("retrieval_score"),
                rerank_score=item.get("rerank_score"),
                chunk_confidence=item.get("chunk_confidence"),
                chunk_confidence_percent=item.get("chunk_confidence_percent"),
                confidence_formula=item.get("confidence_formula"),
                rank=item.get("rank"),
                snippet=str(item.get("snippet") or ""),
            )
        )
    return out


def _parse_trace(raw: Any) -> AnswerTrace | None:
    if not raw:
        return None
    if isinstance(raw, AnswerTrace):
        return raw
    if not isinstance(raw, dict):
        return None
    conf_raw = raw.get("confidence") or {}
    if isinstance(conf_raw, ConfidenceInfo):
        confidence = conf_raw
    elif isinstance(conf_raw, dict):
        confidence = ConfidenceInfo(
            score=float(conf_raw.get("score") or 0),
            percent=int(conf_raw.get("percent") or 0),
            level=str(conf_raw.get("level") or ""),
            factors=conf_raw.get("factors") or {},
        )
    else:
        confidence = ConfidenceInfo()
    return AnswerTrace(
        route=str(raw.get("route") or ""),
        query_type=str(raw.get("query_type") or ""),
        route_method=str(raw.get("route_method") or ""),
        mode=str(raw.get("mode") or ""),
        original_query=str(raw.get("original_query") or ""),
        rewritten_query=str(raw.get("rewritten_query") or ""),
        rewrite_method=str(raw.get("rewrite_method") or ""),
        used_rewrite=bool(raw.get("used_rewrite")),
        use_hybrid=bool(raw.get("use_hybrid")),
        retrieval=raw.get("retrieval") or {},
        reranking=raw.get("reranking") or {},
        generation=raw.get("generation") or {},
        confidence=confidence,
        retrieved_docs=_to_trace_docs(raw.get("retrieved_docs")),
        reranked_docs=_to_trace_docs(raw.get("reranked_docs")),
        model=str(raw.get("model") or ""),
        confidence_percent=int(raw.get("confidence_percent") or confidence.percent or 0),
        confidence_level=str(raw.get("confidence_level") or confidence.level or ""),
    )


def _enrich_document_row(doc: dict[str, Any]) -> dict[str, Any]:
    """UI-friendly document fields without changing registry storage."""
    filename = str(doc.get("filename") or "")
    suffix = Path(filename).suffix.lower().lstrip(".") or "unknown"
    return {
        **doc,
        "file_type": suffix,
        "status": doc.get("status") or "indexed",
        "uploaded_at": doc.get("updated_at") or doc.get("uploaded_at") or "",
    }


def _to_product_response(answer: ChatAnswer | dict[str, Any]) -> ProductChatResponse:
    if isinstance(answer, ChatAnswer):
        citations = [c.model_dump() for c in answer.citations]
        reason = answer.route_reason or ""
        if "casual_chat" in reason:
            qtype = "casual_chat"
        elif citations or "knowledge_query" in reason:
            qtype = "knowledge_query"
        else:
            qtype = ""
        return ProductChatResponse(
            answer=answer.final_answer,
            sources=_citations_to_sources(citations),
            query_type=qtype,
            mode=reason,
            route_method="",
            route=qtype,
            confidence="",
            confidence_percent=0,
            confidence_level="",
            model="",
            final_answer=answer.final_answer,
            citations=citations,
            reasoning_summary=answer.reasoning_summary,
            route_reason=reason,
            relevant_pages=answer.relevant_pages,
            routed_doc_ids=answer.routed_doc_ids,
            conversation_id="",
            memory={},
        )

    citations = answer.get("citations") or []
    text = str(answer.get("answer") or answer.get("final_answer") or "")
    query_type = str(answer.get("query_type") or "")
    mode = str(answer.get("mode") or "")
    route_method = str(answer.get("route_method") or "")
    trace = _parse_trace(answer.get("trace"))
    conf_percent = int(
        answer.get("confidence_percent")
        or (trace.confidence_percent if trace else 0)
        or 0
    )
    conf_level = str(
        answer.get("confidence_level")
        or (trace.confidence_level if trace else "")
        or ""
    )
    confidence_value = answer.get("confidence")
    if confidence_value is None or confidence_value == "":
        confidence_value = conf_percent if conf_percent else ""
    return ProductChatResponse(
        answer=text,
        sources=_citations_to_sources(citations),
        query_type=query_type,
        mode=mode,
        route_method=route_method,
        confidence=confidence_value if not isinstance(confidence_value, dict) else conf_percent,
        confidence_percent=conf_percent,
        confidence_level=conf_level,
        route=str(answer.get("route") or query_type),
        retrieved_docs=_to_trace_docs(answer.get("retrieved_docs") or (trace.retrieved_docs if trace else [])),
        reranked_docs=_to_trace_docs(answer.get("reranked_docs") or (trace.reranked_docs if trace else [])),
        model=str(answer.get("model") or (trace.model if trace else "") or ""),
        trace=trace,
        final_answer=text,
        citations=citations if isinstance(citations, list) else [],
        reasoning_summary=f"{mode}|query_type={query_type}".strip("|"),
        route_reason=str(
            answer.get("route_reason")
            or (f"{query_type}:{route_method}" if query_type else mode)
            or ""
        ),
        relevant_pages=[],
        routed_doc_ids=answer.get("routed_doc_ids") or [],
        conversation_id=str(answer.get("conversation_id") or ""),
        memory=answer.get("memory") if isinstance(answer.get("memory"), dict) else {},
        original_query=str(
            answer.get("original_query")
            or (trace.original_query if trace else "")
            or ""
        ),
        rewritten_query=str(
            answer.get("rewritten_query")
            or (trace.rewritten_query if trace else "")
            or ""
        ),
        rewrite_method=str(
            answer.get("rewrite_method")
            or (trace.rewrite_method if trace else "")
            or ""
        ),
        use_hybrid=bool(
            answer.get("use_hybrid")
            if answer.get("use_hybrid") is not None
            else (trace.use_hybrid if trace else False)
        ),
        session_models=answer.get("session_models")
        if isinstance(answer.get("session_models"), dict)
        else {},
    )


async def _ingest_upload(
    file: UploadFile,
    *,
    model_overrides: SessionModelOverrides | None = None,
) -> dict[str, Any]:
    if not file.filename:
        return {
            "ok": False,
            "status": "rejected",
            "error_code": "INGEST_ERROR",
            "message": "Missing filename",
        }
    if not is_supported(file.filename):
        return {
            "ok": False,
            "status": "rejected",
            "error_code": "INGEST_ERROR",
            "message": (
                f"Unsupported file type. Supported: "
                f"{', '.join(SUPPORTED_SUFFIXES)}"
            ),
        }
    suffix = Path(file.filename).suffix or ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        content = await file.read()
        tmp.write(content)
    try:
        dest = Path(settings.upload_cache_dir) / Path(file.filename).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_path, dest)
        result = ingest_service.ingest_file(dest, model_overrides=model_overrides)
        message = "Document ingested successfully"
        conversion = result.get("conversion") or {}
        if conversion.get("converted"):
            message = (
                f"Converted {conversion.get('from_type')}→{conversion.get('to_type')} "
                f"via {conversion.get('engine')}, then indexed"
            )
        return {
            "ok": True,
            "status": "indexed",
            "filename": result.get("filename"),
            "doc_id": result.get("doc_id"),
            "chunk_count": result.get("chunk_count"),
            "file_type": result.get("file_type"),
            "conversion": conversion,
            "pipeline_steps": result.get("pipeline_steps") or [],
            "session_models": result.get("session_models") or {},
            "message": message,
            **{
                k: v
                for k, v in result.items()
                if k
                not in {
                    "filename",
                    "doc_id",
                    "chunk_count",
                    "file_type",
                    "conversion",
                    "pipeline_steps",
                    "session_models",
                }
            },
        }
    finally:
        tmp_path.unlink(missing_ok=True)


@app.middleware("http")
async def add_request_id(request, call_next):
    rid = bind_request_id(request.headers.get("X-Request-ID"))
    t0 = time.perf_counter()
    logger.info("http_request", method=request.method, path=str(request.url.path))
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("http_unhandled_error", method=request.method, path=str(request.url.path))
        raise
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    response.headers["X-Request-ID"] = rid
    logger.info(
        "http_response",
        method=request.method,
        path=str(request.url.path),
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return response


@app.exception_handler(RagError)
async def rag_error_handler(_, exc: RagError):
    logger.warning("rag_error", error_code=exc.error_code, message=exc.message)
    return JSONResponse(
        status_code=400,
        content={"error_code": exc.error_code, "message": exc.message},
    )


@app.get("/health")
def health():
    ollama = check_ollama_health(settings)
    vector_path = Path(settings.vector_db_path)
    writable = False
    try:
        vector_path.mkdir(parents=True, exist_ok=True)
        probe = vector_path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except Exception as exc:  # noqa: BLE001
        writable = False
        write_error = str(exc)
    else:
        write_error = None

    status = "ok" if ollama.get("ok") and writable else "degraded"
    return {
        "status": status,
        "ollama": ollama,
        "vector_db_path": str(vector_path),
        "vector_db_writable": writable,
        "vector_db_write_error": write_error,
        "documents": ingest_service.registry.count(),
        "chunks": ingest_service.vector_store.count(),
        "models": {
            "llm": settings.llm_model,
            "embed": settings.embed_model,
            "reranker": settings.reranker_model,
            "reranker_backend": settings.reranker_backend,
            "bound_embed_model": ingest_service.vector_store.settings.embed_model,
        },
        "session_model_defaults": defaults_from_settings(settings),
        "flags": {
            "use_query_router": settings.use_query_router,
            "use_reranker": settings.use_reranker,
            "use_bm25": settings.use_bm25,
            "use_query_rewrite": settings.use_query_rewrite,
            "use_conversation_memory": settings.use_conversation_memory,
        },
    }


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    embed_model: str | None = None,
    llm_model: str | None = None,
    reranker_backend: str | None = None,
):
    """Product upload: multi-format → Loader → Chunk → Embed → Vector DB."""
    bind_request_id()
    overrides = SessionModelOverrides.from_mapping(
        {
            "embed_model": embed_model,
            "llm_model": llm_model,
            "reranker_backend": reranker_backend,
        }
    )
    result = await _ingest_upload(file, model_overrides=overrides)
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    logger.info(
        "upload_done",
        filename=result.get("filename"),
        doc_id=result.get("doc_id"),
        chunk_count=result.get("chunk_count"),
        file_type=result.get("file_type"),
    )
    return result


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    """Legacy ingest alias — same pipeline as /upload."""
    bind_request_id()
    result = await _ingest_upload(file)
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    # Preserve legacy shape expected by older Gradio clients.
    return {
        "filename": result.get("filename"),
        "doc_id": result.get("doc_id"),
        "chunk_count": result.get("chunk_count"),
        "status": result.get("status"),
        "ok": True,
    }


@app.get("/session/models")
def get_session_model_defaults():
    """Return .env defaults + currently bound vector-store embed (no secrets)."""
    return {
        "defaults": defaults_from_settings(settings),
        "bound_embed_model": ingest_service.vector_store.settings.embed_model,
        "persisted_to_env": False,
        "note": "Overrides are session-only; Clear chat keeps them; browser refresh resets UI.",
    }


@app.post("/session/models")
def apply_session_models(body: SessionModelsRequest):
    """
    Apply session model choices.
    - embed_model: rebind vector-store embedding for subsequent upload/chat retrieval
    - llm/reranker: acknowledged for clients (applied per /chat request)
    Never writes .env; never accepts API keys.
    """
    bind_request_id()
    overrides = SessionModelOverrides.from_mapping(body.model_dump())
    bind_info = ingest_service.bind_session_embed(overrides.embed_model)
    effective = overrides.apply(settings)
    return {
        "ok": True,
        "persisted_to_env": False,
        "defaults": defaults_from_settings(settings),
        "session_models": overrides.to_public_dict(effective),
        "embed_binding": bind_info,
    }


@app.post("/chat", response_model=ProductChatResponse)
def chat(body: ChatRequest):
    """
    Chat with optional Conversation Memory + session model overrides:
    - input: {\"query\": \"...\", \"conversation_id\": \"...?\", \"llm_model\": \"...?\"}
    - output: {\"answer\", \"sources\", \"conversation_id\", \"session_models\", ...}
    """
    bind_request_id()
    overrides = body.model_overrides()
    logger.info(
        "chat_request",
        query_preview=body.text[:120],
        structured=body.structured,
        conversation_id=body.conversation_id,
        session_override=overrides.has_any(),
    )
    if overrides.embed_model:
        ingest_service.bind_session_embed(overrides.embed_model)
    answer = qa_service.ask(
        body.text,
        structured=body.structured,
        conversation_id=body.conversation_id,
        model_overrides=overrides,
    )
    product = _to_product_response(answer)
    logger.info(
        "chat_response",
        query_type=product.query_type,
        mode=product.mode,
        source_count=len(product.sources),
        conversation_id=product.conversation_id or None,
    )
    return product


@app.post("/reset")
def reset():
    bind_request_id()
    return ingest_service.reset_all()


@app.get("/documents")
def list_docs():
    docs = [_enrich_document_row(d) for d in ingest_service.list_documents()]
    return {"documents": docs}


@app.delete("/documents/{doc_id}")
def delete_doc(doc_id: str):
    bind_request_id()
    return ingest_service.delete_document(doc_id)


@app.post("/compare-retrieval")
def compare_retrieval(body: CompareRequest):
    """Phase2 ablation: dense-only vs dense+rerank."""
    bind_request_id()
    return qa_service.compare_rerank(body.question)


def run():
    import uvicorn

    uvicorn.run(
        "apps.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
