# Enterprise RAG

> 一句话：用本地 LLM + 向量检索，把企业内部文档变成可引用的智能问答服务。  
> One-liner: Turn private enterprise documents into citable Q&A with local LLM + vector retrieval.

**状态 / Status:** Phase1–Phase4 + Enhancement Step1–Step4 完成 · Phase5 Evaluation 完成 · Phase6（云模型）= Future Work  
**架构图 / Architecture:** [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md) · **评测 / Eval:** [`docs/eval.md`](docs/eval.md) · **Docker:** [`docs/docker.md`](docs/docker.md) · **演示:** [`docs/demo_script.md`](docs/demo_script.md)

---

## Index / 索引

| # | 中文 | English |
| --- | --- | --- |
| 1 | [项目介绍](#1-项目介绍) | [Overview](#1-overview-en) |
| 2 | [系统架构图](#2-系统架构图) | [Architecture](#2-architecture-en) |
| 3 | [技术栈](#3-技术栈) | [Tech Stack](#3-tech-stack-en) |
| 4 | [功能展示](#4-功能展示) | [Features](#4-features-en) |
| 5 | [运行方式](#5-运行方式) | [Run](#5-run-en) |
| 6 | [项目结构](#6-项目结构说明) | [Layout](#6-layout-en) |
| 7 | [技术亮点](#7-技术亮点) | [Highlights](#7-highlights-en) |
| 8 | [API](#8-api) | [API](#8-api) |
| 9 | [配置](#9-配置管理) | [Config](#9-config-en) |
| 10 | [相关文档](#10-相关文档) | [Docs](#10-docs-en) |

---

# 中文

## 1. 项目介绍

企业知识分散在手册、规格书与 Office 文档中，通用聊天模型容易编造答案。  
**Enterprise RAG** 提供私有化路径：多格式上传 → 向量入库 → 意图路由 →（可选改写 / Hybrid）检索重排 → 本地 LLM 生成，并返回**引用来源**与 Answer Trace，便于演示、审计与秋招作品集展示。

当前样例评测（Recall@5，视本机索引而定）约 **91.7%**；详见 [`evaluation/phase5_report.md`](evaluation/phase5_report.md)。云端生成/Embedding + Session API Key（Phase6）列为 **Future Work**。

## 2. 系统架构图

```text
User
  ↓
Query Router（规则 + LLM）
  ├── knowledge_query
  │     ↓
  │   Query Rewrite（可选）→ Dense[/Hybrid BM25] → Reranker → Prompt(原问+Memory) → Ollama
  │     → Answer + Sources + Trace
  └── casual_chat
        ↓
      Ollama（跳过检索，可带 Memory）
```

入库：

```text
多格式文件 → [Office 转换] → Loader →（表格 Markdown / 可选 OCR）→ Chunk → Embedding → Chroma + BM25
```

完整 Mermaid 图见 [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md)。

## 3. 技术栈

| 层级 | 技术 |
| --- | --- |
| 编排 / RAG | LangChain |
| 本地 LLM / Embedding | Ollama（如 `qwen2.5:7b` / `nomic-embed-text`） |
| 向量库 | Chroma |
| 语义重排 | DashScope `gte-rerank-v2`（失败回退 Lexical） |
| API | FastAPI |
| Demo UI | Streamlit（另保留 Gradio 薄客户端） |
| 配置 | `.env` + pydantic-settings |
| 部署 | Docker / docker-compose |
| 评测 | CLI Recall@K + RAGAS-style 轻量指标 |

## 4. 功能展示

1. **多格式上传**：pdf / doc(x) / ppt(x) / md / txt；legacy Office 可显式转换  
2. **智能问答**：Query Router 分流知识库 / 闲聊；可选 Query Rewrite、Hybrid（BM25 默认关）  
3. **引用来源 + Trace**：sources、置信度、原问/改写问、Hybrid 开关  
4. **Conversation Memory**：多轮窗口；Clear chat 开新会话  
5. **Session 模型覆盖**：LLM / Embedding / Reranker backend 仅影响当前浏览器会话，不写回 `.env`  
6. **评测**：`python -m apps.cli.main eval`（见 [`docs/eval.md`](docs/eval.md)）

### Demo 截图

| 场景 | 截图 |
| --- | --- |
| 知识库上传 / 已索引文档 | ![Workspace upload](docs/demo/01_workspace_upload.png) |
| 问答 + 引用来源 | ![Q&A with sources](docs/demo/02_qa_sources.png) |
| Answer Trace / 置信度 | ![Answer Trace](docs/demo/03_answer_trace.png) |
| Phase5 评测摘要 | ![Eval summary](docs/demo/04_eval_summary.png) |

演示口述见 [`docs/demo_script.md`](docs/demo_script.md)。重截图（需本机 API+UI 已启动）：`python scripts/capture_demo_screenshots.py`（依赖可选 `playwright`）。

## 5. 运行方式

### 5.1 环境准备

```bash
cd enterprise-rag
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
copy .env.example .env          # 按需填写 DASHSCOPE_API_KEY
```

安装并拉取 Ollama 模型（**本机运行，推荐**）：

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

可选样例 PDF：

```bash
python scripts/make_sample_pdfs.py
python -m apps.cli.main ingest-dir data/samples
```

### 5.2 启动 API

```bash
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

健康检查：`http://127.0.0.1:8000/health`

### 5.3 启动 Streamlit Demo

```bash
streamlit run apps/web/streamlit_app.py --server.port 8501
```

浏览器打开 `http://127.0.0.1:8501`。

### 5.4 Docker / 快速调用

见 [`docs/docker.md`](docs/docker.md)。评测见 [`docs/eval.md`](docs/eval.md)。

```bash
curl -F "file=@data/samples/acme_employee_handbook.pdf" http://127.0.0.1:8000/upload

curl -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"公司的年假政策是什么？\"}"
```

## 6. 项目结构说明

```text
enterprise-rag/
├── apps/
│   ├── api/main.py              # FastAPI
│   ├── web/streamlit_app.py     # Knowledge Workspace UI
│   └── cli/main.py              # ingest-dir / eval / compare
├── src/
│   ├── router/ · query_rewrite/ · reranker/
│   ├── ingestion/ · indexing/ · memory/ · eval/
│   ├── generation/ · services/ · config/
├── data/eval/ · data/samples/
├── evaluation/                  # Phase5 报告输出
├── docs/
└── tests/
```

## 7. 技术亮点

- **Query Router**：知识库走检索链，闲聊直达 LLM  
- **Rewrite + Hybrid（可选）**：换问法更稳；BM25 默认关闭  
- **Reranker**：宽召回 → 语义重排 Top-K  
- **Memory / Trace / Session 模型**：可演示、可解释、会话级覆盖不落盘密钥  
- **评测闭环**：固定题集 + Recall@K + RAGAS-style 报告  
- **本地优先**：生成与向量默认 Ollama；重排可选 DashScope  

## 8. API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/upload` | 多格式上传入库 |
| POST | `/chat` | 问答（可带 conversation_id / session 模型字段） |
| GET/POST | `/session/models` | Session 模型默认值 / 绑定 Embedding |
| GET | `/documents` | 文档列表 |
| DELETE | `/documents/{doc_id}` | 删除文档 |
| POST | `/reset` | 清空索引 |
| POST | `/compare-retrieval` | 重排对比 |

## 9. 配置管理

全部通过 `.env` / 环境变量，由 `src/config/settings.py` 统一读取。  
**禁止**在业务代码中硬编码 API Key。Session UI **不会**把 Key 写回 `.env`。

常用变量：`OLLAMA_BASE_URL`、`LLM_MODEL`、`EMBED_MODEL`、`DASHSCOPE_API_KEY`、`RERANKER_BACKEND`、`USE_BM25`、`USE_QUERY_REWRITE`、`ENABLE_OCR` 等（见 `.env.example`）。

## 10. 相关文档

- [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md) — 架构图  
- [`docs/eval.md`](docs/eval.md) — 评测操作  
- [`docs/docker.md`](docs/docker.md) — Docker / Ollama  
- [`docs/demo_script.md`](docs/demo_script.md) — 演示脚本  
- [`docs/architecture_decisions.md`](docs/architecture_decisions.md) — 架构决策（ADR）  
- [`docs/development_plan.md`](docs/development_plan.md) — 开发计划（含 Phase6 Future Work）  

---

# English

## 1. Overview (EN)

Enterprise documents should not be answered by hallucinating chatbots.  
**Enterprise RAG** is a local-first service: multi-format ingest → route by intent → optional rewrite / hybrid retrieve + rerank → generate with Ollama → return **citable sources** and an Answer Trace.

**Status:** Phases 1–4 + Enhancement Steps 1–4 done · Phase5 Evaluation done · **Phase6 (cloud LLM/Embed + session API key) = Future Work**.  
Sample **Recall@5 ≈ 91.7%** (depends on your local index); see [`docs/eval.md`](docs/eval.md).

## 2. Architecture (EN)

```text
User → Query Router
        → knowledge: Rewrite? → Dense[/Hybrid] → Rerank → Prompt(original+Memory) → Ollama
        → casual: Ollama (+ Memory)
```

Ingest: multi-format → convert → load → tables/OCR → chunk → embed → Chroma (+ BM25 store).

## 3. Tech Stack (EN)

LangChain · Ollama · Chroma · DashScope Reranker · FastAPI · Streamlit · Docker · pydantic-settings · CLI eval

## 4. Features (EN)

- Multi-format upload (pdf/doc/ppt/md/txt) with optional Office convert, table Markdown, OCR  
- Query Router, Memory, Query Rewrite, optional BM25 Hybrid, Reranker  
- Streamlit workspace: Trace, session model overrides (no `.env` write)  
- Evaluation: Recall@K + RAGAS-style metrics via CLI  

### Demo screenshots

| Scene | Screenshot |
| --- | --- |
| Knowledge upload / indexed docs | ![Workspace upload](docs/demo/01_workspace_upload.png) |
| Q&A + sources | ![Q&A with sources](docs/demo/02_qa_sources.png) |
| Answer Trace / confidence | ![Answer Trace](docs/demo/03_answer_trace.png) |
| Phase5 eval snapshot | ![Eval summary](docs/demo/04_eval_summary.png) |

Walkthrough: [`docs/demo_script.md`](docs/demo_script.md). Re-capture: `python scripts/capture_demo_screenshots.py` (optional `playwright`).

## 5. Run (EN)

```bash
pip install -r requirements.txt
copy .env.example .env
ollama pull qwen2.5:7b && ollama pull nomic-embed-text
python -m apps.cli.main ingest-dir data/samples
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
streamlit run apps/web/streamlit_app.py
# eval:
python -m apps.cli.main eval
# or
docker compose up --build
```

Host Ollama is recommended; see [`docs/docker.md`](docs/docker.md).

## 6. Layout (EN)

`apps/` (API + Streamlit + CLI) · `src/router|query_rewrite|reranker|memory|eval|...` · `docs/` · `evaluation/` · `tests/`

## 7. Highlights (EN)

Observable RAG pipeline · modular retrieval enhancements · session-safe model overrides · reproducible eval reports · local-first defaults

## 8. API

Same table as Chinese section. Chat: `{"query":"..."}` → `{"answer","sources",...}`. Optional session model fields and `conversation_id`.

## 9. Config (EN)

All secrets/paths/models via `.env` — no hardcoding; UI session overrides are memory-only.

## 10. Docs (EN)

[`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md) · [`docs/eval.md`](docs/eval.md) · [`docs/docker.md`](docs/docker.md) · [`docs/demo_script.md`](docs/demo_script.md) · [`docs/architecture_decisions.md`](docs/architecture_decisions.md) · [`docs/development_plan.md`](docs/development_plan.md)
