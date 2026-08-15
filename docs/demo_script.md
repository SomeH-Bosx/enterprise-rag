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
2. **上传 / 知识库** — 侧栏「上传文档」独立可见；「知识库列表」默认折叠，展开可看已索引文档与详情。可再传一份样例 PDF。  
3. **知识问答** — 问：`How many annual leave days do ACME full-time employees get?`  
   - 展示答案、Sources、侧栏 Answer Trace（Router / Retrieval / Rerank / Confidence）。  
4. **闲聊路由** — 问：`你好，你是谁？` — 说明走 casual，不检索。  
5. **多轮 Memory / Rewrite** — 先问年假，再问「那病假呢？」；可分别开关 Memory 与 Rewrite（关 Rewrite 后 Trace 中 `改写方法` 应为 `disabled` / `memory_fallback`）。  
6. **Session 模型** — 打开「修改模型」，说明仅当前会话生效、不写 `.env`。  
7. **评测（可选）** — `python -m apps.cli.main eval --skip-generation`，打开 `evaluation/phase5_report.md` 展示 Recall@K。

## 收尾一句话

> 这是本地优先的企业 RAG：FastAPI + Streamlit、可解释 Trace、Memory / Rewrite 会话开关、Dense|BM25|Hybrid，以及可复现的 Phase5 评测——不是只能点一点的 Notebook Demo。后续方向见 README Future Work（含 Phase6）。

## Demo 截图

README「功能展示」已挂图：`docs/demo/01_workspace_upload.png` … `04_eval_summary.png`。

重截（API `:8000` + Streamlit `:8501` 已启动）：

```bash
pip install playwright
playwright install chromium
python scripts/capture_demo_screenshots.py
```
