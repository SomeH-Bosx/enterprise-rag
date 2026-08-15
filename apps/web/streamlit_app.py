"""企业知识工作台 — Streamlit UI。

布局（方案 B）：左侧边栏（知识库 + 模型 + Answer Trace）| 主区聊天
滚动：侧栏与主区使用 Streamlit 原生独立滚动
耗时：仅展示最终秒数（无后台线程刷 UI）
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
from src.retrieval.hybrid import ALLOWED_RETRIEVAL_MODES, resolve_retrieval_mode

settings = get_settings()
API_BASE = settings.api_base_url.rstrip("/")

_RETRIEVAL_MODE_LABELS = {
    "dense": "Dense（向量）",
    "bm25": "BM25（关键词）",
    "hybrid": "Hybrid（Dense+BM25）",
}
_RETRIEVAL_MODE_OPTIONS = ["dense", "bm25", "hybrid"]

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


_HEALTH_CACHE_KEY = "_cache_health"
_DOCS_CACHE_KEY = "_cache_docs"
_STATUS_TTL_S = 30.0


def _client(*, timeout: float = 300.0) -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=timeout, trust_env=False)


def _cache_get(key: str, ttl_s: float) -> Any | None:
    entry = st.session_state.get(key)
    if not isinstance(entry, dict) or "data" not in entry:
        return None
    try:
        age = time.time() - float(entry.get("ts") or 0)
    except (TypeError, ValueError):
        return None
    if age > ttl_s:
        return None
    return entry["data"]


def _cache_set(key: str, data: Any) -> None:
    st.session_state[key] = {"ts": time.time(), "data": data}


def invalidate_status_caches() -> None:
    """Drop health/docs caches after ingest/delete or manual refresh."""
    st.session_state.pop(_HEALTH_CACHE_KEY, None)
    st.session_state.pop(_DOCS_CACHE_KEY, None)
    st.session_state.pop("_health", None)


def fetch_health(*, force: bool = False) -> dict:
    if not force:
        cached = _cache_get(_HEALTH_CACHE_KEY, _STATUS_TTL_S)
        if isinstance(cached, dict):
            return cached
    with _client(timeout=15.0) as client:
        resp = client.get("/health")
        resp.raise_for_status()
        data = resp.json()
    _cache_set(_HEALTH_CACHE_KEY, data)
    return data


def fetch_documents(*, force: bool = False) -> list[dict]:
    if not force:
        cached = _cache_get(_DOCS_CACHE_KEY, _STATUS_TTL_S)
        if isinstance(cached, list):
            return cached
    with _client(timeout=15.0) as client:
        resp = client.get("/documents")
        resp.raise_for_status()
        docs = resp.json().get("documents") or []
    _cache_set(_DOCS_CACHE_KEY, docs)
    return docs


def upload_file(
    file_name: str,
    raw: bytes,
    mime: str | None = None,
    *,
    embed_model: str | None = None,
) -> dict:
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
    params: dict[str, str] = {}
    if embed_model:
        params["embed_model"] = embed_model
    with _client() as client:
        resp = client.post(
            "/upload",
            files={"file": (file_name, raw, content_type)},
            params=params or None,
        )
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


def ask(
    query: str,
    conversation_id: str | None = None,
    *,
    session_models: dict[str, Any] | None = None,
) -> dict:
    payload: dict[str, Any] = {"query": query, "structured": False}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if session_models:
        payload["session_models"] = session_models
        for key in ("llm_model", "embed_model", "reranker_backend", "retrieval_mode"):
            val = session_models.get(key)
            if val:
                payload[key] = val
        # Booleans must use `is not None` — `if False` would drop the override.
        for key in ("use_conversation_memory", "use_query_rewrite"):
            if key in session_models and session_models[key] is not None:
                payload[key] = bool(session_models[key])
    with _client() as client:
        resp = client.post("/chat", json=payload)
    if resp.status_code >= 400:
        return {"ok": False, "message": resp.text}
    data = resp.json()
    data["ok"] = True
    return data


def apply_session_models(models: dict[str, Any]) -> dict:
    with _client() as client:
        resp = client.post("/session/models", json=models)
    if resp.status_code >= 400:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
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
    """在主线程执行阻塞任务；仅展示最终耗时（方案 A）。"""
    box = slot if slot is not None else st.empty()
    box.caption(f"{label} · 进行中…")
    t0 = time.perf_counter()
    try:
        result = fn()
    finally:
        elapsed = time.perf_counter() - t0
        box.caption(f"{label} · 耗时 {elapsed:.1f}s")
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
    if "session_llm_model" not in st.session_state:
        st.session_state.session_llm_model = settings.llm_model
    if "session_embed_model" not in st.session_state:
        st.session_state.session_embed_model = settings.embed_model
    if "session_reranker_backend" not in st.session_state:
        st.session_state.session_reranker_backend = settings.reranker_backend
    if "session_retrieval_mode" not in st.session_state:
        st.session_state.session_retrieval_mode = resolve_retrieval_mode(settings)
    if "session_use_memory" not in st.session_state:
        st.session_state.session_use_memory = bool(settings.use_conversation_memory)
    if "session_use_rewrite" not in st.session_state:
        st.session_state.session_use_rewrite = bool(settings.use_query_rewrite)


def _session_models_payload() -> dict[str, Any]:
    return {
        "llm_model": str(st.session_state.get("session_llm_model") or settings.llm_model).strip(),
        "embed_model": str(st.session_state.get("session_embed_model") or settings.embed_model).strip(),
        "reranker_backend": str(
            st.session_state.get("session_reranker_backend") or settings.reranker_backend
        ).strip(),
        "retrieval_mode": str(
            st.session_state.get("session_retrieval_mode") or resolve_retrieval_mode(settings)
        ).strip().lower(),
        "use_conversation_memory": bool(
            st.session_state.get("session_use_memory", settings.use_conversation_memory)
        ),
        "use_query_rewrite": bool(
            st.session_state.get("session_use_rewrite", settings.use_query_rewrite)
        ),
    }


def _render_chunk_list(items: list[dict[str, Any]], *, limit: int = 8) -> None:
    if not items:
        st.caption("暂无片段。")
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
            st.caption(item.get("confidence_formula") or "公式不可用")
            st.write(
                {
                    "retrieval_score": item.get("retrieval_score"),
                    "rerank_score": item.get("rerank_score"),
                    "chunk_confidence": item.get("chunk_confidence"),
                }
            )
            st.write(item.get("snippet") or "")


def _render_trace_panel(trace_payload: dict[str, Any] | None) -> None:
    st.markdown('<p class="wk-col-title">回答轨迹</p>', unsafe_allow_html=True)
    # st.caption("可观测 RAG · 随侧栏滚动（与聊天区独立）")

    if not trace_payload:
        st.info("提问后可在此查看 Router → Retriever → Reranker → LLM。")
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
    retrieval_mode = (
        trace.get("retrieval_mode")
        or (trace.get("retrieval") or {}).get("retrieval_mode")
        or trace_payload.get("retrieval_mode")
        or ("hybrid" if use_hybrid else "dense")
    )
    hybrid_label = "开" if use_hybrid else "关"
    mode_label = _RETRIEVAL_MODE_LABELS.get(str(retrieval_mode), str(retrieval_mode))
    st.markdown(
        f'<div class="wk-panel"><h4>查询分析</h4>'
        f'<div class="wk-kv">问题类型: <code>{qtype}</code><br/>'
        f"路由方式: <code>{method}</code><br/>"
        f"原问: <code>{original_q}</code><br/>"
        f"改写问: <code>{rewritten_q}</code><br/>"
        f"改写方法: <code>{rewrite_method}</code><br/>"
        f"检索模式: <code>{mode_label}</code><br/>"
        f"Hybrid (BM25): <code>{hybrid_label}</code></div></div>",
        unsafe_allow_html=True,
    )

    retrieval = trace.get("retrieval") or {}
    retrieved_items = trace.get("retrieved_docs") or retrieval.get("items") or []
    top_k = retrieval.get("top_k")
    cand = retrieval.get("candidate_count")
    retriever_name = retrieval.get("retriever") or (
        "Hybrid (Dense + BM25 RRF)"
        if use_hybrid
        else ("BM25 Sparse" if retrieval_mode == "bm25" else "Chroma Dense")
    )
    st.markdown(
        f'<div class="wk-panel"><h4>检索</h4>'
        f'<div class="wk-kv">检索器: <code>{retriever_name}</code><br/>'
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
        f'<div class="wk-panel"><h4>重排</h4>'
        f'<div class="wk-kv">重排器: <code>{reranking.get("reranker") or "—"}</code><br/>'
        f"选用: <code>Top{selected_n if selected_n is not None else '—'}</code></div></div>",
        unsafe_allow_html=True,
    )
    _render_chunk_list(list(reranked_items), limit=8)

    generation = trace.get("generation") or {}
    llm_label = generation.get("llm") or trace.get("model") or trace_payload.get("model") or "—"
    st.markdown(
        f'<div class="wk-panel"><h4>生成</h4>'
        f'<div class="wk-kv">LLM: <code>{llm_label}</code><br/>'
        f"{generation.get('status') or '已生成回答'}</div></div>",
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
        f'<div class="wk-panel"><h4>置信度</h4>'
        f'<div class="{conf_cls}">{percent if percent is not None else "—"}%</div>'
        f'<div class="wk-kv">等级: <b>{level}</b><br/>'
        f'<span class="wk-muted">{factor_line}</span><br/>'
        f'<code style="font-size:0.75rem;white-space:normal;">{formula}</code>'
        f"</div></div>",
        unsafe_allow_html=True,
    )

    with st.expander("原始 Trace（安全字段）", expanded=False):
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
            '<div class="wk-sub">企业知识工作台 · 可观测 RAG</div>',
            unsafe_allow_html=True,
        )

        st.caption(f"API · `{API_BASE}`")
        refresh_cols = st.columns([3, 1])
        with refresh_cols[1]:
            force_status = st.button("刷新", use_container_width=True, help="强制重新拉取 /health 与文档列表")
        if force_status:
            invalidate_status_caches()
        try:
            health = fetch_health(force=force_status)
            st.session_state["_health"] = health
            st.success(f"在线 · 文档={health.get('documents')} · 片段={health.get('chunks')}")
        except Exception as exc:  # noqa: BLE001
            st.session_state["_health"] = None
            invalidate_status_caches()
            st.error(f"API 不可达: {exc}")
            st.info("请先启动 API：`uvicorn apps.api.main:app --host 127.0.0.1 --port 8000`")

        st.divider()
        st.markdown("#### 上传文档")
        uploaded_files = st.file_uploader(
            "上传文档",
            type=["pdf", "doc", "docx", "ppt", "pptx", "md", "txt"],
            accept_multiple_files=True,
            help="支持：pdf/doc/docx/ppt/pptx/md/txt",
            key="kb_uploader",
            label_visibility="collapsed",
        )
        elapsed_slot = st.empty()
        if uploaded_files and st.button("开始入库", type="primary", use_container_width=True):
            ok_n = 0
            fail_rows: list[str] = []
            success_rows: list[dict[str, Any]] = []

            def _batch() -> list[dict[str, Any]]:
                rows: list[dict[str, Any]] = []
                embed = st.session_state.get("session_embed_model") or settings.embed_model
                for f in uploaded_files:
                    result = upload_file(f.name, f.getvalue(), embed_model=embed)
                    rows.append({"name": f.name, "result": result})
                return rows

            with st.spinner("入库中…"):
                rows, elapsed = _run_with_elapsed("入库", _batch, slot=elapsed_slot)
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
                invalidate_status_caches()
                st.rerun()
            for msg in fail_rows:
                st.error(msg)

        report = st.session_state.get("last_ingest_report")
        if report:
            st.success(
                f"已入库 {report.get('ok_n')}/{report.get('total')} 个文件，"
                f"耗时 {float(report.get('elapsed') or 0):.1f}s"
            )
            for row in report.get("success_rows") or []:
                result = row.get("result") or {}
                conv = result.get("conversion") or {}
                steps = result.get("pipeline_steps") or []
                if conv.get("converted"):
                    st.info(
                        f"**{row.get('name')}** · 转换 "
                        f"`{conv.get('from_type')}→{conv.get('to_type')}` "
                        f"引擎 `{conv.get('engine')}` · "
                        f"chunks={result.get('chunk_count')}"
                    )
                with st.expander(
                    f"流水线 · {row.get('name')}",
                    expanded=bool(conv.get("converted")),
                ):
                    for step in steps:
                        st.write(step)
            for msg in report.get("fail_rows") or []:
                st.error(msg)
            if st.button("关闭入库报告", use_container_width=True):
                st.session_state.pop("last_ingest_report", None)
                st.rerun()

        _health_kb = st.session_state.get("_health") or {}
        _doc_n = _health_kb.get("documents")
        _kb_title = f"知识库列表（文档 {_doc_n}）" if _doc_n is not None else "知识库列表"
        with st.expander(_kb_title, expanded=False):
            try:
                docs = fetch_documents(force=force_status)
            except Exception as exc:  # noqa: BLE001
                docs = []
                st.warning(f"无法列出文档: {exc}")

            if not docs:
                st.info("暂无文档。请先上传文件。")
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
                    with st.expander(f"详情 · {fname[:28]}", expanded=False):
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
                    if st.button("删除", key=f"del_{doc_id}", use_container_width=True):
                        out = delete_document(doc_id)
                        if out.get("ok"):
                            st.toast(f"已删除 {fname}")
                            invalidate_status_caches()
                            st.rerun()
                        else:
                            st.error(out.get("message") or "删除失败")

        st.divider()
        st.markdown("#### 模型设置")
        health = st.session_state.get("_health") or {}
        models = health.get("models") or {}
        defaults = health.get("session_model_defaults") or {
            "llm_model": settings.llm_model,
            "embed_model": settings.embed_model,
            "reranker_backend": settings.reranker_backend,
            "retrieval_mode": resolve_retrieval_mode(settings),
        }
        llm = st.session_state.session_llm_model
        embed = st.session_state.session_embed_model
        rerank_backend = st.session_state.session_reranker_backend
        retrieval_mode = str(
            st.session_state.get("session_retrieval_mode") or resolve_retrieval_mode(settings)
        ).strip().lower()
        if retrieval_mode not in ALLOWED_RETRIEVAL_MODES:
            retrieval_mode = resolve_retrieval_mode(settings)
            st.session_state.session_retrieval_mode = retrieval_mode
        bound_embed = models.get("bound_embed_model") or embed
        st.markdown(
            f'<div class="wk-panel"><div class="wk-kv">'
            f"<div><b>LLM</b><br/><code>Ollama:{llm}</code></div><br/>"
            f"<div><b>Embedding</b><br/><code>{embed}</code></div><br/>"
            f"<div><b>Reranker</b><br/><code>{rerank_backend}</code></div><br/>"
            f"<div><b>检索模式</b><br/><code>{_RETRIEVAL_MODE_LABELS.get(retrieval_mode, retrieval_mode)}</code></div><br/>"
            f'<span class="wk-muted">当前向量库 Embedding: <code>{bound_embed}</code> · 仅 session（不写 .env）</span>'
            f"</div></div>",
            unsafe_allow_html=True,
        )

        st.markdown("#### 检索模式")
        st.caption("Dense=向量近邻 · BM25=关键词 · Hybrid=两路 RRF 融合。切换后下一问生效。")
        st.radio(
            "检索模式",
            options=_RETRIEVAL_MODE_OPTIONS,
            format_func=lambda m: _RETRIEVAL_MODE_LABELS.get(m, m),
            key="session_retrieval_mode",
            horizontal=False,
            label_visibility="collapsed",
        )

        st.markdown("#### 多轮 Memory")
        st.toggle(
            "开启 Memory",
            key="session_use_memory",
            help="关闭后本会话不再写入/注入对话历史；清空聊天仍会开新 conversation_id。",
        )
        st.caption("开启后 Prompt 会带近期对话窗口；关闭则每问独立。下一问生效。")

        st.markdown("#### Query Rewrite")
        st.toggle(
            "开启 Rewrite",
            key="session_use_rewrite",
            help="仅影响知识库检索用查询；回答仍用用户原问。",
        )
        st.caption(
            "**作用板块：检索（召回）**，不是最终回答生成。"
            "开启后：在 Dense/BM25/Hybrid 之前，把当前问（可结合历史）改写成更完整的检索问，"
            "用于提高追问/指代场景的召回；**回答 Prompt 仍使用原问**。"
            "关闭后：检索用原问（或仅记忆拼接回退）。闲聊路径不走 Rewrite。下一问生效。"
        )

        with st.expander("修改模型（当前会话）", expanded=False):
            st.caption(
                "仅影响当前浏览器会话。"
                "清空聊天会保留覆盖；刷新页面则恢复 `.env` 默认。"
                "更改 Embedding 后需重新上传文档以保证检索一致。"
                "API Key 仍只放在 `.env`，此处不配置密钥。"
            )
            st.text_input("LLM 模型", key="session_llm_model")
            st.text_input("Embedding 模型", key="session_embed_model")
            st.selectbox(
                "Reranker 后端",
                options=["dashscope", "lexical", "cross_encoder", "auto"],
                key="session_reranker_backend",
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("应用到会话", use_container_width=True):
                    out = apply_session_models(_session_models_payload())
                    if out.get("ok"):
                        st.toast("会话模型已应用（未写入 .env）")
                    else:
                        st.error(out.get("message") or "应用失败")
            with c2:
                if st.button("恢复 .env 默认", use_container_width=True):
                    st.session_state.session_llm_model = defaults.get("llm_model") or settings.llm_model
                    st.session_state.session_embed_model = defaults.get("embed_model") or settings.embed_model
                    st.session_state.session_reranker_backend = (
                        defaults.get("reranker_backend") or settings.reranker_backend
                    )
                    st.session_state.session_retrieval_mode = (
                        defaults.get("retrieval_mode") or resolve_retrieval_mode(settings)
                    )
                    st.session_state.session_use_memory = bool(
                        defaults.get("use_conversation_memory", settings.use_conversation_memory)
                    )
                    st.session_state.session_use_rewrite = bool(
                        defaults.get("use_query_rewrite", settings.use_query_rewrite)
                    )
                    apply_session_models(
                        {
                            "llm_model": st.session_state.session_llm_model,
                            "embed_model": st.session_state.session_embed_model,
                            "reranker_backend": st.session_state.session_reranker_backend,
                            "retrieval_mode": st.session_state.session_retrieval_mode,
                            "use_conversation_memory": st.session_state.session_use_memory,
                            "use_query_rewrite": st.session_state.session_use_rewrite,
                        }
                    )
                    st.toast("已恢复为本会话的 .env 默认值")
                    st.rerun()

        if st.button("清空聊天", use_container_width=True):
            st.session_state.messages = []
            st.session_state.latest_trace = None
            st.session_state.pending_query = None
            st.session_state.conversation_id = None  # 下次提问开启新会话
            # 保留 session 模型覆盖（Step4）
            st.rerun()

        # Scheme B: Trace lives in sidebar → native independent scroll vs main chat
        st.divider()
        _render_trace_panel(st.session_state.latest_trace)


def _render_chat_history() -> None:
    st.markdown('<p class="wk-col-title">工作台对话</p>', unsafe_allow_html=True)
    cid = st.session_state.get("conversation_id")
    mem_on = bool(st.session_state.get("session_use_memory", settings.use_conversation_memory))
    if mem_on:
        st.caption(
            "已开启多轮 Memory · "
            + (f"会话=`{cid[:8]}…`" if cid else "首条消息将创建新会话")
        )
    else:
        st.caption("Memory 已关闭 · 每问独立（不注入历史）")

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
                    with st.expander(f"引用来源（{len(sources)}）", expanded=False):
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
    with st.spinner("路由 → 检索 → 重排 → 生成 …"):
        data, elapsed = _run_with_elapsed(
            "回答",
            lambda: ask(
                query,
                conversation_id=st.session_state.get("conversation_id"),
                session_models=_session_models_payload(),
            ),
            slot=elapsed_slot,
        )

    if not data.get("ok"):
        err = data.get("message") or "对话失败"
        st.session_state.messages.append({"role": "assistant", "content": f"错误: {err}"})
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
        page_title="企业知识工作台",
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

    prompt = st.chat_input("询问你的知识库…")
    if prompt and prompt.strip():
        query = prompt.strip()
        st.session_state.messages.append({"role": "user", "content": query})
        st.session_state.pending_query = query
        st.rerun()


if __name__ == "__main__":
    main()
