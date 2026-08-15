# Enterprise RAG — 架构图（与当前实现对齐）

> **状态：** Phase1–Phase4 + Enhancement Step1–Step4 完成 · Phase5 Evaluation 完成 · **Phase6（云 LLM/Embed + Session API Key）= Future Work**  
> **默认在线链路：**  
> `User → FastAPI / Streamlit → Query Router → (Rewrite? → Dense|BM25|Hybrid → Rerank → Prompt(原问+Memory?) → LLM) | (LLM 直答)`  
> **文档：** [`docs/eval.md`](docs/eval.md) · [`docs/docker.md`](docs/docker.md) · [`docs/demo_script.md`](docs/demo_script.md) · [`docs/development_plan.md`](docs/development_plan.md)

---

## 0. 一句话架构

**本地 Ollama 负责 Embedding 与生成；Chroma 做 Dense 近邻；可选 BM25 / Hybrid(RRF)；DashScope 做语义重排；Query Router 分流知识库与闲聊；Streamlit 提供可观测 Trace、Session 检索模式 / Memory / 模型覆盖。**

---

## 1. 系统总览

```mermaid
flowchart TB
  subgraph Clients["接入层"]
    API["FastAPI<br/>apps/api/main.py"]
    Web["Streamlit Workspace<br/>apps/web/streamlit_app.py"]
    CLI["CLI<br/>apps/cli/main.py"]
    Gradio["Gradio 薄客户端<br/>apps/web/app.py"]
  end

  subgraph Services["服务编排"]
    IngestSvc["IngestService"]
    QASvc["QAService.ask"]
  end

  subgraph IngestPipe["入库"]
    Convert["Office convert 可选"]
    Loader["多格式 Loader"]
    Enrich["Tables / OCR 可选"]
    Splitter["Chunk Splitter"]
    EmbedIn["Ollama Embedding"]
    ChromaWrite["Chroma"]
    BM25Write["BM25 Store"]
    Registry["DocRegistry"]
  end

  subgraph QueryPipe["问答"]
    Router["Query Router"]
    Rewrite["Query Rewrite 可选"]
    Retriever["Dense | BM25 | Hybrid"]
    Reranker["Reranker Facade"]
    Memory["Conversation Memory 可选"]
    Prompt["Prompt + Trace"]
    LLM["Ollama LLM"]
  end

  subgraph External["外部"]
    Ollama["Ollama :11434"]
    DashScope["DashScope gte-rerank-v2"]
    Chroma[(chroma_db/)]
  end

  Web --> API
  Gradio --> API
  API --> IngestSvc
  API --> QASvc
  CLI --> IngestSvc
  CLI --> QASvc

  IngestSvc --> Convert --> Loader --> Enrich --> Splitter --> EmbedIn --> ChromaWrite --> Registry
  Splitter --> BM25Write
  EmbedIn -.-> Ollama
  ChromaWrite --> Chroma

  QASvc --> Router
  Router -->|knowledge| Rewrite --> Retriever --> Reranker --> Prompt --> LLM
  Router -->|casual| Memory --> LLM
  Rewrite --> Memory
  Prompt --> Memory
  Retriever --> Chroma
  Retriever --> BM25Write
  Reranker -.-> DashScope
  LLM -.-> Ollama
```

---

## 2. 在线问答主链路

```mermaid
flowchart TB
  Q["User Query + session 覆盖"] --> QR["Query Router<br/>rules_llm"]
  QR --> CL{"query_type"}

  CL -->|knowledge_query| RW["Query Rewrite<br/>检索用改写问"]
  RW --> MODE{"RETRIEVAL_MODE"}
  MODE -->|dense| D["Chroma Dense Top20"]
  MODE -->|bm25| B["BM25 Sparse Top20"]
  MODE -->|hybrid| H["Dense + BM25 → RRF"]
  D --> RR["Reranker → Top5"]
  B --> RR
  H --> RR
  RR --> P["Prompt 仍用原问 + Memory 窗口"]
  P --> L["Ollama LLM"]
  L --> A["Answer + Sources + Trace"]

  CL -->|casual_chat| M["可选 Memory"]
  M --> L2["Ollama 直答"]
  L2 --> A2["Answer · sources=[]"]
```

```text
User Query（可带 session: retrieval_mode / Memory / 模型）
  ↓
Query Router（规则优先，歧义 LLM）
  ├── knowledge_query
  │     → Query Rewrite（可选；回答仍用原问）
  │     → Dense | BM25 | Hybrid(RRF)   ← Streamlit 可切换
  │     → Rerank Top5（默认 DashScope gte-rerank-v2）
  │     → Prompt(原问 + Memory?) → Ollama
  │     → Answer + Sources + Trace
  └── casual_chat
        → Ollama（跳过检索；可带 Memory）
```

**Session UI（不写 `.env`）：** 检索模式、开启 Memory、LLM/Embedding/Reranker backend。

---

## 3. 入库流水线

```mermaid
flowchart LR
  F["多格式上传"] --> C["convert .doc/.ppt"]
  C --> L["Loader"]
  L --> T["表格 Markdown / OCR"]
  T --> S["Splitter"]
  S --> E["Ollama Embed"]
  E --> V["Chroma"]
  S --> B["BM25 JSON"]
  V --> R["DocRegistry"]
```

```text
pdf/doc/docx/ppt/pptx/md/txt
  → [Office 显式转换]
  → Loader →（表序列化 / 可选 OCR）
  → RecursiveCharacterTextSplitter（CHUNK_SIZE=1000, OVERLAP=150）
  → Embedding → Chroma
  → 同步写入 BM25 store
  → DocRegistry
```

---

## 4. 时序：知识库问答

```mermaid
sequenceDiagram
  participant U as User/Streamlit
  participant API as FastAPI
  participant QA as QAService
  participant QR as QueryRouter
  participant RW as QueryRewriter
  participant RT as Retriever
  participant RR as Reranker
  participant LLM as Ollama

  U->>API: POST /chat (+ session_models)
  API->>QA: ask(q, overrides)
  QA->>QR: route(q)
  QR-->>QA: knowledge_query
  QA->>RW: rewrite(q, history?)
  RW-->>QA: retrieval_query
  QA->>RT: dense|bm25|hybrid (Top20)
  RT-->>QA: candidates
  QA->>RR: rerank → Top5
  Note over RR: 无 Key/失败 → Lexical
  QA->>LLM: prompt(原问 + memory window)
  LLM-->>QA: answer
  QA-->>U: answer + sources + trace
```

---

## 5. 时序：闲聊直答

```mermaid
sequenceDiagram
  participant U as User
  participant QA as QAService
  participant QR as QueryRouter
  participant LLM as Ollama

  U->>QA: ask("你好，你是谁？")
  QA->>QR: route
  QR-->>QA: casual_chat
  Note over QA: 跳过索引检查 / 检索 / 重排
  QA->>LLM: casual prompt (+ Memory?)
  LLM-->>QA: answer
  QA-->>U: sources=[] · Trace 无检索
```

---

## 6. 模块与文件映射

| 组件 | 路径 | 说明 |
| --- | --- | --- |
| 多格式 Loader / 表 / OCR | `src/ingestion/` | Step2 / 3.6 |
| Embedding / Chroma / BM25 / Registry | `src/indexing/` | Phase1 + Hybrid |
| 意图 Router | `src/router/` | Phase3 |
| Dense/BM25/Hybrid + RRF | `src/retrieval/hybrid.py` | `RETRIEVAL_MODE` |
| 文档域 router（未进主链） | `src/retrieval/router.py` | 骨架 |
| PDR（未进主链） | `src/retrieval/pdr.py` | 开关存在未接线 |
| Reranker | `src/reranker/` | dashscope / CE / lexical |
| Query Rewrite | `src/query_rewrite/` | Step3.5 |
| Memory | `src/memory/` | Step3；UI 可关 |
| Trace / Confidence | `src/generation/trace.py` | Step1 |
| Session 覆盖 | `src/config/session_models.py` | Step4 + 检索模式/Memory |
| QA / Ingest | `src/services/` | 编排 |
| Eval | `src/eval/` | Phase5 ragas_lite + Recall |
| API / Streamlit / CLI | `apps/` | Phase4+ |

> **命名：** `src/router/` = 意图路由；`src/retrieval/router.py` = 文件名缩域骨架（主路径 `doc_ids=None`）。

---

## 7. 目录结构（当前）

```text
enterprise-rag/
├── apps/
│   ├── api/main.py                 # FastAPI
│   ├── web/streamlit_app.py        # 主 UI（检索模式 / Memory / Trace）
│   ├── web/app.py                  # Gradio 薄客户端
│   └── cli/main.py                 # ingest-dir / eval / compare
├── src/
│   ├── config/ · ingestion/ · indexing/
│   ├── router/ · query_rewrite/ · memory/
│   ├── retrieval/ · reranker/
│   ├── generation/ · services/ · eval/
├── data/samples/ · data/eval/
├── evaluation/                     # phase5_report · reranker_compare
├── docs/demo/                      # README 截图
├── RAG_ARCHITECTURE.md · README.md
└── requirements.txt
```

---

## 8. 关键配置（默认）

| 配置项 | 默认 | 作用 |
| --- | --- | --- |
| `USE_QUERY_ROUTER` | `true` | 意图路由 |
| `QUERY_ROUTER_MODE` | `rules_llm` | 规则 + LLM |
| `USE_QUERY_REWRITE` | `true` | 检索问改写 |
| `RETRIEVAL_MODE` | 空 | `dense`\|`bm25`\|`hybrid`；空则由 `USE_BM25` 推导 |
| `USE_BM25` | `false` | 兼容：true → 视为 hybrid |
| `USE_RERANKER` | `true` | 重排 |
| `RECALL_TOP_N` / `TOP_K` | `20` / `5` | 宽召回 / 精排截断 |
| `RERANKER_BACKEND` | `dashscope` | 语义重排 |
| `DASHSCOPE_RERANK_MODEL` | `gte-rerank-v2` | 重排模型 |
| `USE_CONVERSATION_MEMORY` | `true` | 多轮 Memory（UI 可关） |
| `EMBED_MODEL` / `LLM_MODEL` | `nomic-embed-text` / `qwen2.5:7b` | Ollama |
| `USE_PDR` | `false` | **未接入主链** |

模型/端口总表见 [`README.md` §3.1](README.md#31-各阶段模型与算法一览)。

---

## 9. Phase 能力边界

| Phase / Step | 状态 | 能力 |
| --- | --- | --- |
| Phase1 | 完成 | 入库 → Dense → LLM |
| Phase2 | 完成 | Top20 → Rerank → Top5 |
| Phase3 | 完成 | Query Router 双链 |
| Phase4 | 完成 | FastAPI + Streamlit + Docker |
| Enhancement 1–4 | 完成 | Trace / 多格式 / Memory / Rewrite / Hybrid / OCR / Session 模型 |
| UI 检索模式 | 完成 | Dense / BM25 / Hybrid + Memory 开关 |
| Phase5 | 完成 | Recall@K + RAGAS-style；样例 Recall@5 ≈ 91.7% |
| Phase6 | Future Work | 云 LLM/Embed + Session API Key |

**有意不做：** Agent / Web Search / SQL / 知识图谱。  
**对外不宣称：** PDR、文档域 router（代码可留、主路径未用）。
