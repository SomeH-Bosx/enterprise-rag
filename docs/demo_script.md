# 2–3 Minute Demo Script

## Setup (before recording)

```bash
cd enterprise-rag
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # or cp
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
python scripts/make_sample_pdfs.py
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Optional UI: `python apps/web/app.py`

## Demo flow (speak while clicking)

1. **Health** — open `http://127.0.0.1:8000/health`, show Ollama ok + empty index.
2. **Ingest two docs** — upload `acme_employee_handbook.pdf` and `beta_product_spec.pdf`.
3. **List documents** — `GET /documents` shows both `doc_id`s (multi-doc, no wipe).
4. **Routed question** — ask: `According to acme_employee_handbook, how many remote work days are allowed per week?`
   - Point at `route_reason=filename_match` and citations.
5. **Cross-doc question** — ask: `What is the p95 latency SLO for Nebula Search Appliance?`
   - Show structured JSON: `final_answer` + `citations`.
6. **Delete one doc** — `DELETE /documents/{doc_id}` for ACME; show Beta still answers.
7. **Eval numbers** — `python -m apps.cli.main eval` and open `data/eval/report.md` (hit@k + page hit rate).

## Closing line

> This is a local-first enterprise RAG: FastAPI service, multi-doc upsert, hybrid retrieval with CrossEncoder rerank, structured citations, and a reproducible mini-eval — not a Gradio-only notebook demo.
