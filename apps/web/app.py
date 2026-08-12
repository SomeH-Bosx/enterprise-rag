from __future__ import annotations

import json
import sys
from pathlib import Path

import gradio as gr
import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings

settings = get_settings()
API_BASE = settings.api_base_url.rstrip("/")


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=300.0)


def refresh_docs() -> str:
    with _client() as client:
        resp = client.get("/documents")
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
    if not docs:
        return "(empty)"
    lines = []
    for d in docs:
        lines.append(
            f"- {d.get('filename')} | doc_id={d.get('doc_id')} | chunks={d.get('chunk_count')}"
        )
    return "\n".join(lines)


def upload_pdf(file_obj) -> tuple[str, str]:
    if file_obj is None:
        return "Please select a PDF", refresh_docs()
    path = Path(file_obj if isinstance(file_obj, str) else file_obj.name)
    with _client() as client:
        with path.open("rb") as f:
            # Prefer Phase4 /upload; /ingest remains as legacy alias.
            resp = client.post("/upload", files={"file": (path.name, f, "application/pdf")})
    if resp.status_code >= 400:
        return f"Ingest failed: {resp.text}", refresh_docs()
    data = resp.json()
    return f"Ingested {data.get('filename')} ({data.get('chunk_count')} chunks)", refresh_docs()


def ask(question: str) -> tuple[str, str]:
    q = (question or "").strip()
    if not q:
        return "Empty question", ""
    with _client() as client:
        resp = client.post("/chat", json={"query": q, "structured": False})
    if resp.status_code >= 400:
        return f"Error: {resp.text}", ""
    data = resp.json()
    answer = data.get("answer") or data.get("final_answer", "")
    meta = {
        "query_type": data.get("query_type"),
        "mode": data.get("mode"),
        "sources": data.get("sources"),
        "citations": data.get("citations"),
        "route_reason": data.get("route_reason"),
    }
    return answer, json.dumps(meta, ensure_ascii=False, indent=2)


def reset_all() -> tuple[str, str]:
    with _client() as client:
        resp = client.post("/reset")
    if resp.status_code >= 400:
        return f"Reset failed: {resp.text}", refresh_docs()
    return "Knowledge base reset.", refresh_docs()


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Enterprise RAG Admin") as demo:
        gr.Markdown("# Enterprise RAG Demo/Admin\nThin Gradio client over FastAPI.")
        with gr.Row():
            file_in = gr.File(label="Upload PDF", file_types=[".pdf"])
            upload_btn = gr.Button("Ingest", variant="primary")
            reset_btn = gr.Button("Reset All", variant="stop")
        status = gr.Textbox(label="Status", interactive=False)
        docs_box = gr.Textbox(label="Documents", lines=8, interactive=False)
        question = gr.Textbox(label="Question")
        ask_btn = gr.Button("Ask")
        answer = gr.Textbox(label="Answer", lines=6)
        citations = gr.Textbox(label="Citations / Meta (JSON)", lines=12)

        upload_btn.click(upload_pdf, inputs=[file_in], outputs=[status, docs_box])
        ask_btn.click(ask, inputs=[question], outputs=[answer, citations])
        question.submit(ask, inputs=[question], outputs=[answer, citations])
        reset_btn.click(reset_all, outputs=[status, docs_box])
        demo.load(refresh_docs, outputs=[docs_box])
    return demo


if __name__ == "__main__":
    ui = build_ui()
    ui.launch(server_name="127.0.0.1", server_port=7860)
