# 2–3 分钟演示脚本

## 录制前准备

```bash
cd enterprise-rag
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
python scripts/make_sample_pdfs.py
python -m apps.cli.main ingest-dir data/samples
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
streamlit run apps/web/streamlit_app.py --server.port 8501
```

## 演示流程（边点边讲）

1. **健康检查** — 打开 `http://127.0.0.1:8000/health`，展示 Ollama 与文档数。  
2. **上传 / 知识库** — Streamlit 侧栏展示已索引文档；可再传一份样例 PDF。  
3. **知识问答** — 问：`How many annual leave days do ACME full-time employees get?`  
   - 展示答案、Sources、侧栏 Answer Trace（Router / Retrieval / Rerank / Confidence）。  
4. **闲聊路由** — 问：`你好，你是谁？` — 说明走 casual，不检索。  
5. **多轮 Memory** — 先问年假，再问「那病假呢？」— 展示 conversation 与改写/检索行为（若开启 Rewrite）。  
6. **Session 模型** — 打开 Change models，说明仅当前会话生效、不写 `.env`。  
7. **评测（可选）** — `python -m apps.cli.main eval --skip-generation`，打开 `evaluation/phase5_report.md` 展示 Recall@K。

## 收尾一句话

> 这是本地优先的企业 RAG：FastAPI + Streamlit、可解释 Trace、Memory、可选 Hybrid/Rewrite，以及可复现的 Phase5 评测报告——不是只能点一点的 Notebook Demo。Phase6 云模型列为 Future Work。
