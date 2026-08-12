"""Enterprise Knowledge Workspace — Streamlit UI.

Layout (Scheme B): Left Sidebar (Knowledge + Models + Answer Trace) | Main Chat
Scroll: Sidebar and Main use Streamlit native independent scroll areas.
Elapsed: final seconds only (no background thread UI updates).
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings

settings = get_settings()
API_BASE = settings.api_base_url.rstrip("/")

_CUSTOM_CSS = """
<style>
    section.main .block-container {
        padding-top: 1rem;
        padding-bottom: 6.5rem;
        max-width: 1100px;
    }
    h3, .stMarkdown h3 {
        overflow: visible !important;
        white-space: normal !important;
        word-break: break-word;
        line-height: 1.25;
        font-size: 1.15rem !important;
    }
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3,
    section[data-testid="stSidebar"] .stMarkdown h4 {
        overflow: visible !important;
        white-space: normal !important;
    }
    .wk-brand {
        font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
        font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em;
        color: #0f2744; margin-bottom: 0.15rem;
    }
    .wk-sub { color: #5a6b7d; font-size: 0.85rem; margin-bottom: 0.8rem; }
    .wk-panel {
        background: linear-gradient(165deg, #f7f9fc 0%, #eef3f8 55%, #e8eef5 100%);
        border: 1px solid #d5dee8; border-radius: 10px;
        padding: 0.85rem 0.95rem; margin-bottom: 0.75rem;
    }
    .wk-panel h4 {
        margin: 0 0 0.45rem 0; font-size: 0.78rem; text-transform: uppercase;
        letter-spacing: 0.06em; color: #3d5268; font-weight: 700;
    }
    .wk-kv { font-size: 0.88rem; color: #1c2b3a; line-height: 1.45; }
    .wk-kv code { background: #e2eaf2; padding: 0.05rem 0.35rem; border-radius: 4px; }
    .wk-conf-high { color: #0d7a4f; font-weight: 700; font-size: 1.35rem; }
    .wk-conf-med { color: #b36b00; font-weight: 700; font-size: 1.35rem; }
    .wk-conf-low { color: #b42318; font-weight: 700; font-size: 1.35rem; }
    .wk-doc-card {
        background: #fff; border: 1px solid #d8e0ea; border-radius: 8px;
        padding: 0.55rem 0.65rem; margin-bottom: 0.35rem;
    }
    .wk-muted { color: #6b7c8f; font-size: 0.8rem; }
    .wk-col-title {
        font-size: 1.12rem; font-weight: 700; color: #0f2744;
        margin: 0 0 0.2rem 0; overflow: visible; white-space: normal;
    }
    [data-testid="stChatMessage"] { border-radius: 10px; }
</style>
"""


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=300.0, trust_env=False)


def fetch_health() -> dict:
    with _client() as client:
        resp = client.get("/health")
        resp.raise_for_status()
        return resp.json()


def fetch_documents() -> list[dict]:
    with _client() as client:
        resp = client.get("/documents")
        resp.raise_for_status()
        return resp.json().get("documents") or []


def upload_file(file_name: str, raw: bytes, mime: str | None = None) -> dict:
    suffix = Path(file_name).suffix.lower()
    mime_map = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".md": "text/markdown",
        ".txt": "text/plain",
    }
    content_type = mime or mime_map.get(suffix, "application/octet-stream")
    with _client() as client:
        resp = client.post("/upload", files={"file": (file_name, raw, content_type)})
    if resp.status_code >= 400:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"ok": False, "message": resp.text}
    return resp.json()


def delete_document(doc_id: str) -> dict:
    with _client() as client:
        resp = client.delete(f"/documents/{doc_id}")
    if resp.status_code >= 400:
        return {"ok": False, "message": resp.text}
    data = resp.json()
    data["ok"] = True
    return data


def ask(query: str, conversation_id: str | None = None) -> dict:
    payload: dict[str, Any] = {"query": query, "structured": False}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    with _client() as client:
        resp = client.post("/chat", json=payload)
    if resp.status_code >= 400:
        return {"ok": False, "message": resp.text}
    data = resp.json()
    data["ok"] = True
    return data


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return iso[:16]


def _run_with_elapsed(label: str, fn: Callable[[], Any], slot: Any | None = None) -> tuple[Any, float]:
    """Run blocking work on the main thread; show final elapsed only (Scheme A)."""
    box = slot if slot is not None else st.empty()
    box.caption(f"{label} · running…")
    t0 = time.perf_counter()
    try:
        result = fn()
    finally:
        elapsed = time.perf_counter() - t0
        box.caption(f"{label} · elapsed {elapsed:.1f}s")
    return result, elapsed


def _init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages: list[dict[str, Any]] = []
    if "latest_trace" not in st.session_state:
        st.session_state.latest_trace = None
    if "pending_query" not in st.session_state:
        st.session_state.pending_query = None
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None


def _render_chunk_list(items: list[dict[str, Any]], *, limit: int = 8) -> None:
    if not items:
        st.caption("No chunks.")
        return
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        name = item.get("filename") or item.get("doc_id") or "chunk"
        rank = item.get("rank")
        pct = item.get("chunk_confidence_percent")
        conf = item.get("chunk_confidence")
        head = f"**#{rank or '—'} {name}** · page={item.get('page')}"
        if pct is not None:
            head += f" · chunk conf **{pct}%**"
        elif conf is not None:
            head += f" · chunk conf **{conf}**"
        with st.expander(head, expanded=False):
            st.caption(item.get("confidence_formula") or "formula n/a")
            st.write(
                {
                    "retrieval_score": item.get("retrieval_score"),
                    "rerank_score": item.get("rerank_score"),
                    "chunk_confidence": item.get("chunk_confidence"),
                }
            )
            st.write(item.get("snippet") or "")


def _render_trace_panel(trace_payload: dict[str, Any] | None) -> None:
    st.markdown('<p class="wk-col-title">Answer Trace</p>', unsafe_allow_html=True)
    st.caption("Observable RAG · scrolls with sidebar (independent from chat)")

    if not trace_payload:
        st.info("Ask a question to inspect Router → Retriever → Reranker → LLM.")
        return

    raw = trace_payload.get("trace") if isinstance(trace_payload.get("trace"), dict) else None
    trace = raw if isinstance(raw, dict) else {
        "query_type": trace_payload.get("query_type") or trace_payload.get("route"),
        "route_method": trace_payload.get("route_method"),
        "retrieval": {},
        "reranking": {},
        "generation": {"llm": trace_payload.get("model"), "status": "Response Generated"},
        "confidence": {
            "percent": trace_payload.get("confidence_percent"),
            "level": trace_payload.get("confidence_level"),
            "factors": {},
        },
        "retrieved_docs": trace_payload.get("retrieved_docs") or [],
        "reranked_docs": trace_payload.get("reranked_docs") or [],
        "model": trace_payload.get("model"),
    }

    qtype = trace.get("query_type") or trace_payload.get("query_type") or "—"
    method = trace.get("route_method") or trace_payload.get("route_method") or "—"
    original_q = (
        trace.get("original_query")
        or trace_payload.get("original_query")
        or "—"
    )
    rewritten_q = (
        trace.get("rewritten_query")
        or trace_payload.get("rewritten_query")
        or original_q
    )
    rewrite_method = (
        trace.get("rewrite_method")
        or trace_payload.get("rewrite_method")
        or "—"
    )
    use_hybrid = trace.get("use_hybrid")
    if use_hybrid is None:
        use_hybrid = trace_payload.get("use_hybrid")
    hybrid_label = "on" if use_hybrid else "off"
    st.markdown(
        f'<div class="wk-panel"><h4>Query Analysis</h4>'
        f'<div class="wk-kv">Query Type: <code>{qtype}</code><br/>'
        f"Route Method: <code>{method}</code><br/>"
        f"Original: <code>{original_q}</code><br/>"
        f"Rewritten: <code>{rewritten_q}</code><br/>"
        f"Rewrite Method: <code>{rewrite_method}</code><br/>"
        f"Hybrid (BM25): <code>{hybrid_label}</code></div></div>",
        unsafe_allow_html=True,
    )

    retrieval = trace.get("retrieval") or {}
    retrieved_items = trace.get("retrieved_docs") or retrieval.get("items") or []
    top_k = retrieval.get("top_k")
    cand = retrieval.get("candidate_count")
    retriever_name = retrieval.get("retriever") or ("Hybrid (Dense + BM25 RRF)" if use_hybrid else "Chroma Dense")
    st.markdown(
        f'<div class="wk-panel"><h4>Retrieval</h4>'
        f'<div class="wk-kv">Retriever: <code>{retriever_name}</code><br/>'
        f"Top-K = <code>{top_k if top_k is not None else '—'}</code>"
        f"{f' · candidates={cand}' if cand is not None else ''}<br/>"
        f'<span class="wk-muted">{retrieval.get("note") or ""}</span>'
        f"</div></div>",
        unsafe_allow_html=True,
    )
    _render_chunk_list(list(retrieved_items), limit=8)

    reranking = trace.get("reranking") or {}
    reranked_items = trace.get("reranked_docs") or reranking.get("items") or []
    selected_n = reranking.get("selected_top_n")
    st.markdown(
        f'<div class="wk-panel"><h4>Reranking</h4>'
        f'<div class="wk-kv">Reranker: <code>{reranking.get("reranker") or "—"}</code><br/>'
        f"Selected: <code>Top{selected_n if selected_n is not None else '—'}</code></div></div>",
        unsafe_allow_html=True,
    )
    _render_chunk_list(list(reranked_items), limit=8)

    generation = trace.get("generation") or {}
    llm_label = generation.get("llm") or trace.get("model") or trace_payload.get("model") or "—"
    st.markdown(
        f'<div class="wk-panel"><h4>Generation</h4>'
        f'<div class="wk-kv">LLM: <code>{llm_label}</code><br/>'
        f"{generation.get('status') or 'Response Generated'}</div></div>",
        unsafe_allow_html=True,
    )

    conf = trace.get("confidence") or {}
    if not isinstance(conf, dict):
        conf = {}
    percent = conf.get("percent", trace_payload.get("confidence_percent"))
    level = conf.get("level") or trace_payload.get("confidence_level") or "—"
    level_l = str(level).lower()
    conf_cls = "wk-conf-med"
    if level_l == "high":
        conf_cls = "wk-conf-high"
    elif level_l == "low":
        conf_cls = "wk-conf-low"
    factors = conf.get("factors") if isinstance(conf.get("factors"), dict) else {}
    formula = factors.get("formula") or ""
    factor_bits = []
    for key in ("retrieval", "rerank", "source_coverage", "grounding"):
        if factors.get(key) is not None:
            factor_bits.append(f"{key}={factors.get(key)}")
    factor_line = " · ".join(factor_bits)
    st.markdown(
        f'<div class="wk-panel"><h4>Confidence</h4>'
        f'<div class="{conf_cls}">{percent if percent is not None else "—"}%</div>'
        f'<div class="wk-kv">Level: <b>{level}</b><br/>'
        f'<span class="wk-muted">{factor_line}</span><br/>'
        f'<code style="font-size:0.75rem;white-space:normal;">{formula}</code>'
        f"</div></div>",
        unsafe_allow_html=True,
    )

    with st.expander("Raw trace (safe fields)", expanded=False):
        st.json(
            {
                "route": qtype,
                "confidence": percent,
                "confidence_level": level,
                "confidence_formula": formula,
                "model": llm_label,
                "retrieved_docs": retrieved_items,
                "reranked_docs": reranked_items,
                "retrieval": retrieval,
                "reranking": reranking,
                "generation": generation,
            }
        )


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown('<div class="wk-brand">Enterprise RAG</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="wk-sub">Knowledge Workspace · Observable RAG</div>',
            unsafe_allow_html=True,
        )

        st.caption(f"API · `{API_BASE}`")
        try:
            health = fetch_health()
            st.session_state["_health"] = health
            st.success(f"Online · docs={health.get('documents')} · chunks={health.get('chunks')}")
        except Exception as exc:  # noqa: BLE001
            st.session_state["_health"] = None
            st.error(f"API unreachable: {exc}")
            st.info("Start API: `uvicorn apps.api.main:app --host 127.0.0.1 --port 8000`")

        st.divider()
        st.markdown("#### Knowledge Base")

        uploaded_files = st.file_uploader(
            "Upload documents",
            type=["pdf", "doc", "docx", "ppt", "pptx", "md", "txt"],
            accept_multiple_files=True,
            help="Multi-format ingest: pdf/doc/docx/ppt/pptx/md/txt",
            key="kb_uploader",
        )
        elapsed_slot = st.empty()
        if uploaded_files and st.button("Index selected", type="primary", use_container_width=True):
            ok_n = 0
            fail_rows: list[str] = []
            success_rows: list[dict[str, Any]] = []

            def _batch() -> list[dict[str, Any]]:
                rows: list[dict[str, Any]] = []
                for f in uploaded_files:
                    result = upload_file(f.name, f.getvalue())
                    rows.append({"name": f.name, "result": result})
                return rows

            with st.spinner("Indexing…"):
                rows, elapsed = _run_with_elapsed("Indexing", _batch, slot=elapsed_slot)
            for row in rows:
                result = row["result"]
                if result.get("ok"):
                    ok_n += 1
                    success_rows.append(row)
                else:
                    fail_rows.append(f"{row['name']}: {result.get('message') or 'failed'}")
            st.session_state["last_ingest_report"] = {
                "elapsed": elapsed,
                "ok_n": ok_n,
                "total": len(rows),
                "success_rows": success_rows,
                "fail_rows": fail_rows,
            }
            if ok_n:
                st.rerun()
            for msg in fail_rows:
                st.error(msg)

        report = st.session_state.get("last_ingest_report")
        if report:
            st.success(
                f"Indexed {report.get('ok_n')}/{report.get('total')} file(s) "
                f"in {float(report.get('elapsed') or 0):.1f}s"
            )
            for row in report.get("success_rows") or []:
                result = row.get("result") or {}
                conv = result.get("conversion") or {}
                steps = result.get("pipeline_steps") or []
                if conv.get("converted"):
                    st.info(
                        f"**{row.get('name')}** · convert "
                        f"`{conv.get('from_type')}→{conv.get('to_type')}` "
                        f"via `{conv.get('engine')}` · "
                        f"chunks={result.get('chunk_count')}"
                    )
                with st.expander(
                    f"Pipeline · {row.get('name')}",
                    expanded=bool(conv.get("converted")),
                ):
                    for step in steps:
                        st.write(step)
            for msg in report.get("fail_rows") or []:
                st.error(msg)
            if st.button("Dismiss ingest report", use_container_width=True):
                st.session_state.pop("last_ingest_report", None)
                st.rerun()

        try:
            docs = fetch_documents()
        except Exception as exc:  # noqa: BLE001
            docs = []
            st.warning(f"Cannot list documents: {exc}")

        if not docs:
            st.info("No documents yet. Upload files to start.")
        else:
            for d in docs:
                fname = d.get("filename") or "unknown"
                ftype = (d.get("file_type") or Path(fname).suffix.lstrip(".") or "pdf").upper()
                status = d.get("status") or "indexed"
                uploaded_at = _fmt_time(d.get("uploaded_at") or d.get("updated_at"))
                doc_id = d.get("doc_id") or ""
                st.markdown(
                    f'<div class="wk-doc-card">'
                    f"<strong>{fname}</strong><br/>"
                    f'<span class="wk-muted">{ftype} · {status} · {uploaded_at}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                with st.expander(f"Info · {fname[:28]}", expanded=False):
                    st.json(
                        {
                            "filename": d.get("filename"),
                            "file_type": d.get("file_type"),
                            "status": d.get("status"),
                            "uploaded_at": d.get("uploaded_at") or d.get("updated_at"),
                            "doc_id": d.get("doc_id"),
                            "chunk_count": d.get("chunk_count"),
                            "source": d.get("source"),
                        }
                    )
                if st.button("Delete", key=f"del_{doc_id}", use_container_width=True):
                    out = delete_document(doc_id)
                    if out.get("ok"):
                        st.toast(f"Deleted {fname}")
                        st.rerun()
                    else:
                        st.error(out.get("message") or "Delete failed")

        st.divider()
        st.markdown("#### Model Settings")
        health = st.session_state.get("_health") or {}
        models = health.get("models") or {}
        llm = models.get("llm") or settings.llm_model
        embed = models.get("embed") or settings.embed_model
        rerank_backend = models.get("reranker_backend") or settings.reranker_backend
        st.markdown(
            f'<div class="wk-panel"><div class="wk-kv">'
            f"<div><b>LLM</b><br/><code>Ollama:{llm}</code></div><br/>"
            f"<div><b>Embedding</b><br/><code>{embed}</code></div><br/>"
            f"<div><b>Reranker</b><br/><code>{rerank_backend}</code></div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        with st.expander("Change models", expanded=False):
            st.caption(
                "Session-level override comes later (Model Configuration). "
                "Values below are from `.env` / Settings (read-only)."
            )
            st.text_input("LLM", value=f"Ollama:{llm}", disabled=True)
            st.text_input("Embedding", value=str(embed), disabled=True)
            st.text_input("Reranker", value=str(rerank_backend), disabled=True)

        if st.button("Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.latest_trace = None
            st.session_state.pending_query = None
            st.session_state.conversation_id = None  # new conversation on next ask
            st.rerun()

        # Scheme B: Trace lives in sidebar → native independent scroll vs main chat
        st.divider()
        _render_trace_panel(st.session_state.latest_trace)


def _render_chat_history() -> None:
    st.markdown('<p class="wk-col-title">Workspace Chat</p>', unsafe_allow_html=True)
    cid = st.session_state.get("conversation_id")
    st.caption(
        "Multi-turn memory enabled · "
        + (f"conversation=`{cid[:8]}…`" if cid else "new conversation on first message")
    )

    for msg in st.session_state.messages:
        role = msg.get("role", "user")
        with st.chat_message(role):
            st.markdown(msg.get("content") or "")
            if role == "assistant":
                sources = msg.get("sources") or []
                meta = msg.get("meta") or ""
                if meta:
                    st.caption(meta)
                if sources:
                    with st.expander(f"Sources ({len(sources)})", expanded=False):
                        for i, src in enumerate(sources, start=1):
                            title = src.get("filename") or src.get("doc_id") or f"source-{i}"
                            page = src.get("page")
                            score = src.get("score")
                            head = f"**{i}. {title}** · page={page}"
                            if score is not None:
                                head += f" · score={score}"
                            st.markdown(head)
                            st.write(src.get("snippet") or "")


def _handle_pending_query() -> None:
    query = st.session_state.pending_query
    if not query:
        return
    st.session_state.pending_query = None

    elapsed_slot = st.empty()
    with st.spinner("Router → Retriever → Reranker → LLM …"):
        data, elapsed = _run_with_elapsed(
            "Answering",
            lambda: ask(query, conversation_id=st.session_state.get("conversation_id")),
            slot=elapsed_slot,
        )

    if not data.get("ok"):
        err = data.get("message") or "Chat failed"
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {err}"})
        st.session_state.latest_trace = None
        st.rerun()
        return

    if data.get("conversation_id"):
        st.session_state.conversation_id = data["conversation_id"]

    answer = data.get("answer") or data.get("final_answer") or ""
    sources = data.get("sources") or []
    conf_p = data.get("confidence_percent")
    conf_l = data.get("confidence_level")
    mem = data.get("memory") or {}
    meta = (
        f"route=`{data.get('route') or data.get('query_type')}` · "
        f"method=`{data.get('route_method')}` · "
        f"model=`{data.get('model')}` · "
        f"confidence=`{conf_p}% ({conf_l})` · "
        f"elapsed=`{elapsed:.1f}s`"
    )
    if mem:
        meta += f" · memory_msgs=`{mem.get('stored_messages')}`"
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "meta": meta,
            "trace": data,
        }
    )
    st.session_state.latest_trace = data
    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Enterprise Knowledge Workspace",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
    _init_state()
    _render_sidebar()

    # Main = chat only (Scheme B). Trace scrolls inside the sidebar.
    _render_chat_history()
    if st.session_state.pending_query:
        _handle_pending_query()

    prompt = st.chat_input("Ask about your knowledge base…")
    if prompt and prompt.strip():
        query = prompt.strip()
        st.session_state.messages.append({"role": "user", "content": query})
        st.session_state.pending_query = query
        st.rerun()


if __name__ == "__main__":
    main()
