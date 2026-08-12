# Enterprise RAG

> 一句话：用本地 LLM + 向量检索，把企业内部 PDF 变成可引用的智能问答服务。  
> One-liner: Turn private enterprise PDFs into citable Q&A with local LLM + vector retrieval.

**状态 / Status:** Phase1–Phase4 complete · Phase5 evaluation pending  
**架构图 / Architecture:** [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md)  
**进度 / Progress:** [`docs/progress.md`](docs/progress.md) · **Docker:** [`docs/docker.md`](docs/docker.md)

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

企业知识分散在 PDF 手册与规格书中，通用聊天模型容易编造答案。  
**Enterprise RAG** 提供私有化路径：上传文档 → 向量入库 → 按问题类型路由 → 检索重排 → 本地 LLM 生成，并返回**引用来源**，便于演示与审计。

## 2. 系统架构图

```text
User
  ↓
Query Router（规则 + LLM）
  ├── knowledge_query
  │     ↓
  │   Retriever（Chroma Top-20）
  │     ↓
  │   Reranker（DashScope → Top-5）
  │     ↓
  │   Prompt Builder
  │     ↓
  │   Ollama LLM → Answer + Sources
  └── casual_chat
        ↓
      Ollama LLM（跳过检索）
```

入库：

```text
PDF → Loader → Chunk → Embedding → Chroma
```

完整 Mermaid 图见 [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md)。

## 3. 技术栈

| 层级 | 技术 |
| --- | --- |
| 编排 / RAG | LangChain |
| 本地 LLM / Embedding | Ollama（`qwen2.5:7b` / `nomic-embed-text`） |
| 向量库 | Chroma |
| 语义重排 | DashScope `gte-rerank-v2`（失败回退 Lexical） |
| API | FastAPI |
| Demo UI | Streamlit（另保留 Gradio 薄客户端） |
| 配置 | `.env` + pydantic-settings |
| 部署 | Docker / docker-compose |

## 4. 功能展示

1. **PDF 上传**：`POST /upload` 触发解析、切分、向量化、入库  
2. **智能问答**：`POST /chat` 经 Query Router 分流知识库 / 闲聊  
3. **引用来源**：返回 `sources[]`（文件名、页码、片段）  
4. **Streamlit Demo**：上传、提问、展示答案与引用  

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
```

### 5.2 启动 API

```bash
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

健康检查：`http://127.0.0.1:8000/health`

### 5.3 启动 Streamlit Demo

另开终端：

```bash
streamlit run apps/web/streamlit_app.py --server.port 8501
```

浏览器打开 `http://127.0.0.1:8501`。

### 5.4 Docker 一键启动（API + UI）

推荐：**Ollama 跑在宿主机**，容器只跑 Python 应用。

```bash
docker compose up --build
```

- API: http://127.0.0.1:8000  
- UI: http://127.0.0.1:8501  

说明与可选「Ollama 容器化」见 [`docs/docker.md`](docs/docker.md)。

### 5.5 快速调用示例

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
│   ├── api/main.py              # FastAPI（/upload /chat /health）
│   ├── web/streamlit_app.py     # Streamlit Demo【Phase4】
│   ├── web/app.py               # Gradio 薄客户端（可选）
│   └── cli/                     # 命令行工具
├── src/
│   ├── router/                  # Query Router
│   ├── reranker/                # DashScope / Lexical
│   ├── ingestion/ · indexing/   # 入库与向量
│   ├── generation/              # Prompt / LLM
│   ├── services/                # Ingest / QA 编排
│   └── config/                  # Settings / Logging
├── tests/
├── docs/                        # plan / progress / docker
├── data/samples/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## 7. 技术亮点

- **Query Router**：知识库问题走检索链，闲聊直达 LLM，降低无效检索  
- **Reranker**：宽召回 Top-20 → 语义重排 Top-5，提升上下文质量  
- **模块化设计**：Router / Retriever / Reranker / LLM 解耦，便于替换后端  
- **本地 LLM 部署**：Embedding + 生成走 Ollama，数据不出本机（重排可选云端）  
- **可展示工程化**：FastAPI + Streamlit + Docker + 统一 JSON 日志  

## 8. API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/upload` | 上传 PDF（产品接口） |
| POST | `/ingest` | 上传 PDF（兼容旧客户端） |
| POST | `/chat` | 问答：`{"query"}` → `{"answer","sources"}` |
| GET | `/documents` | 文档列表 |
| DELETE | `/documents/{doc_id}` | 删除文档 |
| POST | `/reset` | 清空索引 |
| POST | `/compare-retrieval` | 重排对比 |

## 9. 配置管理

全部通过 `.env` / 环境变量，由 `src/config/settings.py` 统一读取。  
**禁止**在业务代码中硬编码 API Key、模型名或路径。

| 变量 | 含义 |
| --- | --- |
| `OLLAMA_BASE_URL` | Ollama 地址 |
| `LLM_MODEL` / `EMBED_MODEL` | 生成 / 向量模型 |
| `VECTOR_DB_PATH` | Chroma 路径 |
| `DASHSCOPE_API_KEY` | 重排 Key |
| `RERANKER_BACKEND` | dashscope / lexical / … |
| `USE_QUERY_ROUTER` | 意图路由开关 |
| `API_BASE_URL` | UI 访问 API 的地址 |
| `LOG_LEVEL` | 日志级别 |

## 10. 相关文档

- [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md) — 最终架构图  
- [`docs/progress.md`](docs/progress.md) — 分阶段进度  
- [`docs/development_plan.md`](docs/development_plan.md) — 开发计划  
- [`docs/docker.md`](docs/docker.md) — Docker / Ollama 说明  

---

# English

## 1. Overview (EN)

Enterprise PDFs should not be answered by hallucinating chatbots.  
**Enterprise RAG** is a local-first service: ingest PDFs → route by intent → retrieve + rerank → generate with Ollama → return **citable sources**.

## 2. Architecture (EN)

```text
User → Query Router
        → knowledge: Retriever → Reranker → Prompt → Ollama
        → casual: Ollama
```

See [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md) for diagrams.

## 3. Tech Stack (EN)

LangChain · Ollama · Chroma · DashScope Reranker · FastAPI · Streamlit · Docker · pydantic-settings

## 4. Features (EN)

- PDF upload & indexing  
- Smart Q&A with Query Router  
- Source citations in API & Streamlit UI  

## 5. Run (EN)

```bash
pip install -r requirements.txt
copy .env.example .env
ollama pull qwen2.5:7b && ollama pull nomic-embed-text
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
streamlit run apps/web/streamlit_app.py
# or
docker compose up --build
```

Host Ollama is recommended; see [`docs/docker.md`](docs/docker.md).

## 6. Layout (EN)

`apps/` (API + Streamlit) · `src/router|reranker|services|...` · `docs/` · `tests/`

## 7. Highlights (EN)

Query Router · semantic Reranker · modular pipelines · local LLM · demo-ready packaging

## 8. API

Same table as Chinese section above. Chat body: `{"query":"..."}` → `{"answer","sources"}`.

## 9. Config (EN)

All secrets/paths/models via `.env` — no hardcoding in application code.

## 10. Docs (EN)

[`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md) · [`docs/progress.md`](docs/progress.md) · [`docs/docker.md`](docs/docker.md)
