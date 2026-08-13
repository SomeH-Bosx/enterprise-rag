# Development Progress

> 规则：每完成一个 Phase，在本文件追加检查记录。  
> 对照计划：[`development_plan.md`](development_plan.md)

---

## Phase1

状态：
完成


实现：

- PDF Loader
- Text Splitter
- Chroma
- Ollama（Embedding + LLM）
- Dense Similarity Retrieval
- Context Stuff + 拒答 Prompt
- Ingest / QA Service 编排
- FastAPI `/ingest` `/chat`（Phase1 可用，工程化主体属 Phase4）


### 1. 已完成的功能

| 能力 | 说明 | 验收 |
| --- | --- | --- |
| PDF 上传与缓存 | 文件落入 `upload_cache/` | 通过 |
| 文档解析 | PDFPlumberLoader 提取文本 | 通过 |
| Chunk 切分 | RecursiveCharacterTextSplitter（中文 separators） | 通过 |
| Embedding | Ollama `nomic-embed-text` | 通过（768 维） |
| 向量保存 | Chroma 持久化 | 通过 |
| 相似度检索 | Chroma similarity_search Top-K | 通过 |
| 问答生成 | Ollama `qwen2.5:7b` + 上下文拼接 | 通过 |

端到端实测：入库 `acme_employee_handbook.pdf` 后提问年假天数，回答为 **15 days annual leave**。


### 2. 当前项目目录结构

```text
enterprise-rag/
├── apps/
│   ├── api/main.py          # FastAPI 入口
│   ├── web/app.py           # Gradio 薄客户端（未作为 Phase1 验收重点）
│   └── cli/main.py          # CLI（eval/compare，后续阶段用）
├── src/
│   ├── config/              # Settings / 日志 / 本地代理绕过
│   ├── ingestion/           # Loader + Splitter  【Phase1 核心】
│   ├── indexing/            # Embedding + Chroma(+BM25骨架)  【Phase1 核心】
│   ├── retrieval/           # Router/Hybrid/Rerank 骨架（默认关闭）
│   ├── generation/          # Prompt / LLM / 后处理
│   ├── services/            # IngestService / QAService  【Phase1 核心】
│   └── eval/                # 评测（Phase5）
├── data/
│   ├── samples/             # 样例 PDF
│   └── eval/                # 评测题集
├── docs/
│   ├── development_plan.md
│   ├── progress.md          # 本文件
│   └── ...
├── scripts/make_sample_pdfs.py
├── requirements.txt
├── .env.example
├── Dockerfile / docker-compose.yml
└── README.md
```


### 3. 核心调用流程（Phase1）

```text
PDF
  → load_pdf (PDFPlumberLoader)
  → split_documents (RecursiveCharacterTextSplitter)
  → OllamaEmbeddings.embed_documents
  → Chroma.add_documents
  → DocRegistry 记录 doc_id

Question
  → OllamaEmbeddings.embed_query
  → Chroma.similarity_search(k=TOP_K)
  → build_context + build_simple_prompt
  → OllamaLLM.generate
  → Answer
```

服务入口：

- `IngestService.ingest_pdf()` → 入库
- `QAService.ask(structured=False)` → 默认 naive dense（`USE_BM25/RERANKER/PDR=false`）


### 4. 已实现模块对应文件

| 模块 | 文件 |
| --- | --- |
| PDF Loader | `src/ingestion/loaders.py` |
| Text Splitter | `src/ingestion/splitters.py` |
| Embedding | `src/indexing/embeddings.py` |
| Vector DB (Chroma) | `src/indexing/vectorstore.py` |
| 文档注册表 | `src/indexing/doc_registry.py` |
| 入库编排 | `src/services/ingest_service.py` |
| 问答编排 | `src/services/qa_service.py` |
| Prompt | `src/generation/prompts/templates.py` |
| LLM Gateway | `src/generation/llm_gateway.py` |
| 配置 / 代理绕过 | `src/config/settings.py` |
| API | `apps/api/main.py` |
| 样例数据 | `data/samples/*.pdf` |


### 5. 存在的问题或技术债务

- **超前骨架未启用**：`router` / `hybrid` / `reranker` / `bm25_store` / `pdr` 代码已存在，但 Phase1 默认关闭；需在后续 Phase 正式接线与验收，避免“有文件无能力”的错觉。
- **系统代理干扰 Ollama**：本机 `httpx trust_env=True` 访问 `127.0.0.1:11434` 曾返回 502；已用 `NO_PROXY`/`bypass_local_proxy()` 规避，部署文档需写明。
- **样例 PDF 过短**：当前 demo PDF 几乎单 chunk，无法充分验证切分/多段检索质量。
- **包初始化曾循环导入**：`services.__init__` / `ingestion.__init__` 已改为轻量导出；后续新增模块需避免再引入环依赖。
- **Phase1 未强制 UI/Docker 验收**：API/Gradio/Compose 文件在仓库中，但不属于 Phase1 验收门禁。
- **结构化输出默认关闭**：`/chat` 默认 `structured=false`，与后续可审计答案目标尚未对齐（留给后续阶段）。


### 6. 是否满足进入下一阶段条件

| 条件（来自 Phase1 验收） | 结果 |
| --- | --- |
| 上传一个 PDF | 满足 |
| 可回答 PDF 中的问题 | 满足（实测年假 15 天） |
| 数据流 Loader→Split→Embed→Chroma→Retrieve→LLM→Answer | 满足 |

**结论：可以进入 Phase2（Reranker）。**


遇到问题：

#### 问题 A：循环导入，无法单独测试文档处理

| 项 | 内容 |
| --- | --- |
| **现象** | `from src.ingestion.loaders import load_pdf` 报错：`ImportError: cannot import name 'load_pdf' from partially initialized module ... (circular import)` |
| **原因** | `loaders.py` 引入 `src.services.exceptions` → 触发 `services/__init__.py` 再导入 `IngestService` → `IngestService` 又导入 `loaders`，形成环 |
| **解决** | 将 `src/services/__init__.py`、`src/ingestion/__init__.py` 改为轻量包初始化（不在 `__init__` 重导出重型类），打断环依赖；业务实现文件本身不动主干逻辑 |

#### 问题 B：本地 Ollama Embedding/LLM 调用返回 502

| 项 | 内容 |
| --- | --- |
| **现象** | `langchain-ollama` / `httpx` 访问 `http://127.0.0.1:11434/api/embed` 得到 **502**；同时 `ollama run nomic-embed-text`、`curl` 直连却正常 |
| **原因** | Python `httpx` 默认 `trust_env=True`，会走系统 HTTP 代理；代理把本机 `127.0.0.1` 流量错误转发，导致网关 502。对比实验：`trust_env=False` → 200，`trust_env=True` → 502 |
| **解决** | 在配置启动阶段设置 `NO_PROXY/no_proxy` 包含 `127.0.0.1,localhost,::1`（`bypass_local_proxy()`），并让 Embedding/LLM/health 检查在调用前执行该绕过；健康检查客户端使用 `trust_env=False` |

#### 问题 C：样例 PDF 过短，切分/检索难验证

| 项 | 内容 |
| --- | --- |
| **现象** | 初期 `acme`/`beta` 样例几乎只有 1 个 chunk，Phase1 能问答，但难以观察多段召回行为 |
| **原因** | 演示 PDF 文本量远小于 `CHUNK_SIZE=1000`，Splitter 不会产生多块 |
| **解决** | Phase1 先用短样例完成闭环验收；多 chunk 噪声样例放到 Phase2（`enterprise_knowledge_mix.pdf`）再补齐，避免阻塞 MVP |


下一阶段：

Reranker

（Phase2：Vector Search top20 → Reranker → Top5 → LLM；需对比加入前后回答质量）

---

## Phase2

状态：
完成（含 DashScope 语义重排增强；已用有效 API Key 做 live 验收）


实现：

- 独立 Reranker 包 `src/reranker/`
- Dense Recall Top-K（`RECALL_TOP_N=20`）
- Rerank 后取 Top-N（`TOP_K=5`）
- **默认语义重排：`RERANKER_BACKEND=dashscope` + `DASHSCOPE_RERANK_MODEL=gte-rerank-v2`**
- 保留 CrossEncoder / Lexical；Key 缺失或 API 失败时 fallback → Lexical
- 上层接口不变：统一 `rerank(query, documents, top_n)`
- 对比产物：`evaluation/reranker_compare.md`（live）、`docs/retrieval_ablation.md`
- Phase1 能力在 `USE_RERANKER=false` / `naive` 路径下保持可用


### 1. 已完成的功能

| 能力 | 说明 | 验收 |
| --- | --- | --- |
| 向量宽召回 | `similarity_search(k=RECALL_TOP_N)`，不改 VectorStore 核心 | 通过 |
| 独立 Reranker 模块 | `BaseReranker` + Facade + 多 backend | 通过 |
| DashScope 语义重排 | `TextReRank.call(model=gte-rerank-v2)` | **live 通过** |
| 重排截断 | Rerank 后保留 Top-N 交给 LLM | 通过 |
| Fallback | Key/API 失败 → Lexical | 单测通过 |
| 前后对比 | Baseline Top-K vs Top20→Rerank→Top5 | 通过（见 evaluation） |
| 不破坏 Phase1 | 上传/切分/Embedding/Chroma/naive 问答仍可用 | 通过 |


### 2. 当前项目目录结构（Phase2 增量）

```text
src/reranker/
├── __init__.py
├── base.py                   # BaseReranker（rerank 接口）
├── facade.py                 # 统一入口（按 RERANKER_BACKEND 分发）
├── dashscope_reranker.py     # 【增强】DashScope 语义重排
├── cross_encoder.py          # 本地 CrossEncoder（备用）
├── lexical.py                # 离线词法重排（fallback）
└── lexical_reranker.py       # 别名模块
src/services/qa_service.py    # dense → rerank → LLM 接线
scripts/generate_reranker_compare.py
evaluation/reranker_compare.md
docs/retrieval_ablation.md
# （已移除冗余）scripts/phase2_compare_rerank.py → 请用 CLI `compare` 或 generate_reranker_compare.py
tests/test_dashscope_reranker.py
tests/test_rag_dashscope_rerank_flow.py
```


### 3. 核心调用流程（Phase2）

```text
Question
  → Vector Retriever 召回 Top-K (RECALL_TOP_N=20)
  → DashScope Reranker（语义打分重排；失败则 Lexical）
  → 选择 Top-N (TOP_K=5)
  → Context 拼接
  → Ollama LLM
  → Answer
```


### 4. 已实现模块对应文件

| 模块 | 文件 |
| --- | --- |
| Reranker 抽象 | `src/reranker/base.py` |
| Facade（上层统一入口） | `src/reranker/facade.py`（`Reranker` / 兼容名 `CrossEncoderReranker`） |
| DashScope 语义重排 | `src/reranker/dashscope_reranker.py` |
| CrossEncoder Reranker | `src/reranker/cross_encoder.py` |
| Lexical Reranker | `src/reranker/lexical.py` / `lexical_reranker.py` |
| QA 接线 | `src/services/qa_service.py` |
| 配置 | `src/config/settings.py` + `.env`（`DASHSCOPE_API_KEY`, `RERANKER_BACKEND=dashscope`） |
| 对比产物 | `evaluation/reranker_compare.md` |
| 兼容 shim | `src/retrieval/reranker.py` |


### 5. Live 测试记录（有效 DASHSCOPE_API_KEY）

测试时间：配置有效 Key 后执行（不改业务代码）。

| 测试项 | 命令/方式 | 结果 |
| --- | --- | --- |
| 配置加载 | Settings 读取 | `backend=dashscope`，`model=gte-rerank-v2`，Key 已加载 |
| 单元/流程测试 | `pytest tests/test_dashscope_reranker.py tests/test_rag_dashscope_rerank_flow.py tests/test_reranker.py -q` | **5 passed** |
| Live 单测烟雾 | 3 候选文档直调 `DashScopeReranker` | Top1=`signal`，score≈**0.9615**，`reranker=dashscope` |
| 端到端对比报告 | `python scripts/generate_reranker_compare.py` | **dashscope_mode=live**，写入 `evaluation/reranker_compare.md` |

Live 对比摘要（问题：p95 latency SLO）：

- Baseline / Rerank 最终答案均正确：`under 200 milliseconds`
- DashScope Top1：`beta_product_spec`，score≈**0.905**
- 噪声块分数显著更低（如 handbook ≈0.006）
- chunk 顺序相对 baseline **发生变化**（`Order changed: True`）


### 6. 存在的问题或技术债务

- **依赖云端 API Key**：DashScope 不可用时会 fallback Lexical，语义质量下降；需监控失败日志。
- **本地 CrossEncoder 仍难用**：HuggingFace 拉取不稳定，仅作备用 backend，不再作为默认。
- **未启用 BM25 Hybrid / Router / PDR**：留给后续 Phase。
- **样例语料偏合成**：演示可用，上真实业务文档前需替换评测集。
- **安全**：`.env` 含密钥，勿提交到公开仓库。


### 7. 是否满足进入下一阶段条件

| 条件（Phase2 验收） | 结果 |
| --- | --- |
| 在基础 RAG 上增加 Reranker | 满足 |
| 流程为 Vector Top20 → Rerank → Top5 → LLM | 满足 |
| 重排为语义级（非仅 lexical） | **满足（DashScope live）** |
| 可对比 rerank 前后结果/回答 | 满足（`evaluation/reranker_compare.md`） |
| 未破坏 Phase1 能力 | 满足 |
| 未越界实现 Router/Agent/Docker/Eval 系统 | 满足 |

**结论：Phase2（含 DashScope 增强）完成，可以进入 Phase3（Query Router）。**


遇到问题：

#### 问题 D（增强修复）：默认 Lexical 非语义级重排

| 项 | 内容 |
| --- | --- |
| **现象** | Phase2 初验收时默认 `RERANKER_BACKEND=lexical`，排序非语义级 |
| **原因** | 本机 HuggingFace 不可达，无法稳定加载本地 CrossEncoder 权重 |
| **解决** | 升级为 DashScope `TextReRank` API（默认 `dashscope` + `gte-rerank-v2`）；Key/API 失败 fallback Lexical；上层仍只调用 `rerank()`。已用有效 Key 完成 live 验收 |

#### 问题 A：CrossEncoder 模型无法从 HuggingFace 下载

| 项 | 内容 |
| --- | --- |
| **现象** | 加载 `BAAI/bge-reranker-base` 时反复报 `WinError 10060`（连接超时） |
| **原因** | 运行环境访问 `huggingface.co` 不稳定或被阻断 |
| **解决** | 不再依赖 HF 作为默认路径；改为 DashScope API 语义重排，Lexical 仅作 fallback；CrossEncoder 代码保留可选 |

#### 问题 B：初次词法重排分数被停用词/弱特征干扰

| 项 | 内容 |
| --- | --- |
| **现象** | Lexical 回退时噪声 chunk 有时得分接近相关块 |
| **原因** | 初版 overlap 未充分过滤停用词 |
| **解决** | 收紧词法打分；主路径改用 DashScope 后，该问题仅影响 fallback 场景 |

#### 问题 C：短样例无法体现 Rerank 价值

| 项 | 内容 |
| --- | --- |
| **现象** | 仅 1–2 个短 PDF 时重排前后差异不明显 |
| **原因** | 候选集过小，几乎没有重排空间 |
| **解决** | 增加 `enterprise_knowledge_mix.pdf` 多 chunk 噪声语料，并用 live 对比报告验证排序变化 |


下一阶段：

Query Router

（Phase3：按问题类型路由到不同 Chain）

---

## Phase3

状态：
完成


实现：

- Query Router（独立模块 `src/router/`）
- Query Classification（规则优先 + LLM 歧义回退）
- Multiple Chain Routing（`knowledge_query` / `casual_chat`）
- 主调用链入口接入 Router（`QAService.ask`）
- 配置项：`USE_QUERY_ROUTER` / `QUERY_ROUTER_MODE`
- 测试：`tests/test_query_router.py`


### 1. Phase3 已经完成的功能

| 能力 | 说明 | 验收 |
| --- | --- | --- |
| 独立 Router 模块 | `src/router/router.py` + `classifier.py`，未写入 Retriever/Reranker/LLM | 通过 |
| 结构化输出 | `{"query_type": "knowledge_query" \| "casual_chat"}` | 通过 |
| knowledge_query 链 | Router → Retriever → Reranker → Prompt → LLM | 通过 |
| casual_chat 链 | Router → LLM 直接回答（跳过检索/重排） | 通过 |
| 案例1 知识库问题 | 「公司的年假政策是什么？」→ knowledge_query | 通过 |
| 案例2 闲聊问题 | 「你好，你是谁？」→ casual_chat，不进入检索 | 通过 |
| 不破坏 Phase1/2 | PDF/Embedding/Chroma/Reranker/Ollama 路径保持；可 `USE_QUERY_ROUTER=false` 关闭 | 通过 |


### 2. 当前项目目录结构（Phase3 增量）

```text
src/router/
├── __init__.py
├── router.py                 # QueryRouter 入口，输出 RouteResult
└── classifier.py             # 规则 + LLM 分类
src/services/qa_service.py    # ask() 以 Router 为入口分流
src/generation/prompts/templates.py  # build_casual_prompt
src/config/settings.py        # USE_QUERY_ROUTER / QUERY_ROUTER_MODE
tests/test_query_router.py
```

说明：`src/retrieval/router.py` 仍是 Phase 早期「按文件名缩检索域」骨架，与 Phase3 Query Router **不是同一模块**。


### 3. 核心调用流程（Phase3）

```text
User Query
  ↓
Query Router（规则优先，歧义时 LLM）
  ↓
判断 query_type
  ├── knowledge_query
  │     ↓
  │   Retriever（Top20）
  │     ↓
  │   Reranker（Top5）
  │     ↓
  │   Prompt
  │     ↓
  │   LLM
  │
  └── casual_chat
        ↓
      LLM 直接回答（无检索）
```


### 4. 已实现模块对应文件

| 模块 | 文件 | 作用 |
| --- | --- | --- |
| Query Router | `src/router/router.py` | 入口路由，输出结构化 `query_type` |
| Query Classifier | `src/router/classifier.py` | 规则/LLM 意图分类 |
| QA 接线 | `src/services/qa_service.py` | Router 后分流 knowledge / casual |
| Casual Prompt | `src/generation/prompts/templates.py` | 闲聊提示词 |
| 配置 | `src/config/settings.py`、`.env.example` | Router 开关与模式 |
| 测试 | `tests/test_query_router.py` | 分类 + 链道路由验收 |


### 5. 存在的问题或技术债务

- **规则覆盖有限**：未见关键词的歧义 query 依赖 LLM；LLM 失败时默认 `knowledge_query`（偏检索安全）。
- **命名并存**：`src/retrieval/router.py`（文档域）与 `src/router/`（意图）需在文档中持续区分，避免误用。
- **未扩展多意图**：SQL / Web Search / Agent Tool 仅预留扩展位，本阶段未实现。
- **闲聊无会话记忆**：casual 路径为单轮直答，无多轮上下文。


### 6. 是否满足进入 Phase4 的条件

| 条件（Phase3 验收） | 结果 |
| --- | --- |
| 独立 Query Router 模块 | 满足 |
| 按 query 类型选择不同流程 | 满足（knowledge / casual） |
| 知识库问题进入检索链 | 满足 |
| 闲聊不进入检索 | 满足 |
| 未破坏 Phase1/2 | 满足（相关单测 16 passed） |
| 未越界实现 Agent / Web Search / SQL / Docker 工程化主体 | 满足 |

**结论：Phase3 完成，可以进入 Phase4（工程化展示：FastAPI/前端/Docker/README 等）。当前停止，等待下一步指令。**


遇到问题：

#### 问题 A：仓库内已有 `retrieval/router.py`，易与 Query Router 混淆

| 项 | 内容 |
| --- | --- |
| **现象** | `src/retrieval/router.py` 实现的是按文件名匹配缩检索域，不是意图路由 |
| **原因** | Phase1 骨架超前放置，命名同为 router |
| **解决** | Phase3 新建独立包 `src/router/`；旧模块保留不动，避免破坏既有测试与未来文档域路由能力 |

#### 问题 B：纯 LLM 分类不稳定且增加延迟

| 项 | 内容 |
| --- | --- |
| **现象** | 每次问答先调分类 LLM 会增加时延，且解析偶发失败 |
| **原因** | 小模型输出格式不完全稳定 |
| **解决** | 采用 **规则 + LLM**：明确闲聊/知识库由规则快速判定；歧义再走 LLM；解析失败默认 `knowledge_query` |


下一阶段：

工程化（Phase4：FastAPI/前端界面/Docker/README/Demo）

---

## Phase4

状态：
完成


实现：

- FastAPI 产品接口（`POST /upload`、`POST /chat` → `answer` + `sources`）
- Streamlit Demo（上传 / 提问 / 回答 / 引用来源）
- Docker / docker-compose（API + UI；推荐宿主机 Ollama）
- Logging 完善（请求、Router、召回数、Rerank、LLM 耗时、异常）
- 配置统一（`.env` + Settings：Key / 模型 / 路径 / Reranker / UI）
- README 双语完善


### 1. Phase4 已经完成的功能

| 能力 | 说明 | 验收 |
| --- | --- | --- |
| API 上传 | `POST /upload`：PDF → Loader → Chunk → Embed → Chroma；返回文件状态 | 通过 |
| API 问答 | `POST /chat` 接受 `query`，返回 `answer` + `sources`；兼容 `question` | 通过 |
| Streamlit UI | `apps/web/streamlit_app.py`：上传、提问、展示答案与引用 | 通过 |
| 配置管理 | Key/模型/路径/Reranker/API_BASE_URL/LOG_LEVEL 均走 `.env` | 通过 |
| 统一日志 | request_id + Router/Retriever/Reranker/LLM 耗时 + 异常栈 | 通过 |
| Docker | Dockerfile + compose（api/ui）；`docs/docker.md` 说明本机 Ollama | 通过 |
| README | 介绍 / 架构 / 技术栈 / 功能 / 运行 / 结构 / 亮点 | 通过 |
| 不破坏 Phase1–3 | Router/Reranker/入库核心流程未改设计；回归测试通过 | 通过 |


### 2. 当前项目目录结构（Phase4 增量）

```text
apps/
├── api/main.py                 # /upload /chat 产品契约
└── web/
    ├── streamlit_app.py        # 【Phase4】Streamlit Demo
    └── app.py                  # Gradio 薄客户端（保留）
src/config/
├── settings.py                 # + API_BASE_URL / STREAMLIT_PORT / LOG_LEVEL
└── logging.py                  # 可配置 LOG_LEVEL
src/generation/schemas.py       # ProductChatResponse / SourceItem
docs/docker.md                  # Docker + 本机 Ollama 说明
docker-compose.yml              # api + ui（ollama 可选 profile）
Dockerfile
README.md
tests/test_api_phase4.py
```


### 3. 完整系统调用流程

```text
User（Streamlit / curl / Gradio）
  ↓
FastAPI
  ├── POST /upload → IngestService → Loader → Chunk → Embed → Chroma
  └── POST /chat
        ↓
      Query Router
        ├── knowledge_query → Retriever → Reranker → Prompt → Ollama → answer + sources
        └── casual_chat → Ollama → answer（sources=[]）
```


### 4. 已实现模块对应文件

| 模块 | 文件 | 作用 |
| --- | --- | --- |
| 产品 API | `apps/api/main.py` | `/upload` `/chat` `/health` |
| Streamlit Demo | `apps/web/streamlit_app.py` | 可演示 UI |
| 产品响应模型 | `src/generation/schemas.py` | `answer` + `sources` |
| 配置 | `src/config/settings.py` · `.env.example` | 统一环境配置 |
| 日志 | `src/config/logging.py` · `qa_service.py` | 链路计时与异常 |
| Docker | `Dockerfile` · `docker-compose.yml` · `docs/docker.md` | 一键部署说明 |
| README | `README.md` | 项目说明与运行指南 |


### 5. 存在的问题或技术债务

- **Ollama 默认不进应用镜像**：模型大、GPU 依赖强；推荐宿主机运行（已文档化）。compose `with-ollama` profile 可选但偏重。
- **DashScope Key 仍依赖外部**：无 Key 时 Reranker 回退 Lexical，语义质量下降。
- **Streamlit 依赖 API 进程**：需先起 FastAPI；Docker 下由 compose `depends_on` 串联。
- **Demo 截图已入库**：`docs/demo/*.png`（上传 / 问答+Sources / Trace / Phase5 摘要）；README 中英文「功能展示」已挂图；重截脚本 `scripts/capture_demo_screenshots.py`。
- **Phase5 评测未做**：Recall / RAGAS 系统化评测留给下一阶段。


### 6. 是否满足项目发布 / 进入下一阶段条件

| 条件 | 结果 |
| --- | --- |
| 可展示 API + UI | 满足 |
| Docker 可启动 Python 应用 | 满足 |
| README 可从零运行 | 满足 |
| 未破坏 Phase1–3 | 满足 |
| 未越界实现 Agent / Web Search / SQL / 知识图谱 | 满足 |
| 系统化 Evaluation（Phase5） | 未做（有意） |

**结论：Phase4 完成，可作为 Demo 展示发布；系统化评测属 Phase5。当前停止，等待下一步指令。**


遇到问题：

#### 问题 A：Compose 原先默认 USE_BM25=true 与 Phase2/3 默认不一致

| 项 | 内容 |
| --- | --- |
| **现象** | 旧 `docker-compose.yml` 打开 BM25，与主路径默认关闭不符 |
| **原因** | 早期骨架残留 |
| **解决** | 对齐 `.env` 默认：`USE_BM25=false`，并补齐 Router / Reranker 环境变量 |

#### 问题 B：Ollama 容器化不适合默认一键演示

| 项 | 内容 |
| --- | --- |
| **现象** | 镜像体积与模型拉取拖慢演示，GPU 透传不稳定 |
| **原因** | LLM 权重不属于应用代码层 |
| **解决** | 默认 compose 连接宿主机 Ollama；可选 `--profile with-ollama`；详见 `docs/docker.md` |

#### 问题 C：旧 `/chat` 字段与产品契约不一致

| 项 | 内容 |
| --- | --- |
| **现象** | 历史接口用 `question` / `final_answer` / `citations` |
| **原因** | Phase1 结构化答案模型 |
| **解决** | 接受 `query|question`；统一返回 `answer` + `sources`，同时保留兼容字段 |


下一阶段：

项目优化与展示 / Phase5 Evaluation（需确认后再开始）

---

## Phase4 Enhancement

状态：
完成（Step1–Step4 均完成）

**路线前瞻：**

| Phase | 内容 | 状态 |
| --- | --- | --- |
| **Phase5** | Evaluation（Recall / RAGAS-style / 测试集） | **完成** |
| **Phase6** | DashScope 云 LLM + 云 Embedding + Session API Key（Clear chat 保留 Key） | **未开始 ← 下一个** |

详见 [`development_plan.md`](development_plan.md) · 评测操作：[`eval.md`](eval.md)


### 阶段拆分（已确认）

| Step | 内容 | 状态 |
| --- | --- | --- |
| **Step1** | Knowledge Workspace UI + Trace + **UI 打磨包** | **完成** |
| **Step2** | 多格式 Document Loader（pdf/doc/docx/ppt/pptx/md/txt） | **完成** |
| **Step3** | Conversation Memory | **完成** |
| **Step3.5** | Query Rewrite / Hybrid（换问法鲁棒性） | **完成** |
| **Step3.6** | 表格序列化 + OCR（解析增强） | **完成** |
| **Step4** | Session 模型配置管理 | **完成** |

说明：Query Rewrite / Hybrid 作为独立 Step，插在 Memory 之后、表格/OCR 之前。


**Step1 UI 打磨包覆盖原反馈：**

1. 标题裁切修复  
2. 仅显示已用秒数（不做伪进度）  
3. PDF 批量上传  
4. Chunk 置信度 + 公式链路展示；答案置信度校准更符合直觉  
5. Chunk 截断：保持现状（可行），Trace 注明 character splitter  
6. 解析能力说明保留；表格/OCR → Step3.6  
7. Info 改为文档旁 expander  
8. `chat_input` 提到页面级吸底  

**并进 Step2：** 多格式 Loader（批量上传自然扩展到多类型）。


实现进度：

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Knowledge Workspace UI | **完成** | Sidebar / Chat；Trace 在侧栏；计时最终耗时 |
| Answer Trace + Confidence | **完成** | 答案级校准 + chunk 级公式 |
| Multi-format Document Loader | **完成（Step2）** | pdf/doc/docx/ppt/pptx/md/txt 统一 Loader |
| Conversation Memory | **完成（Step3）** | conversation_id + 窗口截断 + UI 续聊 |
| Query Rewrite / Hybrid | **完成（Step3.5）** | Rewrite 检索用；Hybrid 默认关 |
| Table serialization + OCR | **完成（Step3.6）** | Markdown 表；OCR=tesseract 默认开 |
| Model Configuration | **完成（Step4）** | Session 覆盖；不写回 .env |


### Step1：UI Workspace + Trace Panel

#### 修改文件与原因

| 文件 | 原因 | 影响 |
| --- | --- | --- |
| `apps/web/streamlit_app.py` | 重构为 Enterprise Knowledge Workspace 三栏布局 | UI 体验；不改 RAG 核心算法 |
| `src/generation/trace.py` | **新增** Confidence 计算 + Answer Trace 组装 | 可解释输出；无密钥/Prompt 泄露 |
| `src/generation/schemas.py` | 扩展 `ProductChatResponse` / `AnswerTrace` | API 契约向后兼容增强 |
| `src/services/qa_service.py` | ask() 附加 trace；召回附带 retrieval_score | 响应多字段；检索路径不变 |
| `src/indexing/vectorstore.py` | 新增 `similarity_search_with_score` | 供 Confidence 使用 |
| `src/retrieval/reranker.py` | 新增 `dense_with_scores` | 兼容旧 `naive_dense_only` |
| `apps/api/main.py` | 映射 trace；文档列表补 file_type/status/uploaded_at | `/chat` `/documents` 更利于 UI |
| `tests/test_answer_trace.py` | Confidence / Trace 单测 | 回归保障 |
| `tests/test_api_phase4.py` | 断言 trace 字段 | API 契约验收 |


#### Confidence 计算方式（打磨后）

答案级（更符合直觉）：

- Retriever（top-heavy + `sim^0.65` 校准）**25%**
- Reranker（0.7×top1 + 0.3×mean(top3)）**50%**
- Source 覆盖（1 个来源即可满）**10%**
- Grounding **15%**
- Level：`≥65 High` / `≥45 Medium` / 其余 `Low`

Chunk 级：

- 有双分：`0.4×retrieval + 0.6×rerank`
- Trace 展示 `confidence_formula`


#### 当前系统调用流程（Step1 后）

```text
User
  ↓
Knowledge Workspace（Streamlit：Sidebar | Chat | Trace）
  ↓
FastAPI /chat
  ↓
Query Router
  ├── knowledge_query → Retriever(+scores) → Reranker → Prompt → LLM
  └── casual_chat → LLM
  ↓
ProductChatResponse
  { answer, sources, route, confidence, retrieved_docs, reranked_docs, model, trace }
  ↓
UI：中间渲染回答/引用；右侧 Trace Panel 展示 Router/Retrieval/Rerank/Generation/Confidence
```


#### Step1 打磨包（本轮）

| 文件 | 修改原因 | 影响 |
| --- | --- | --- |
| `apps/web/streamlit_app.py` | 标题/列宽/吸底输入/Info expander/批量 PDF/已用秒数/chunk 公式 UI | 仅 UI 与交互 |
| `src/generation/trace.py` | 置信度校准 + chunk confidence/formula | 分数更直觉；契约字段增加 |
| `src/generation/schemas.py` | TraceDocItem 扩展分数字段 | API 兼容增强 |
| `src/services/qa_service.py` | `expected_sources=1` | 单源命中不再被 source 项压分 |
| `apps/api/main.py` | 映射新 trace 字段 | 透传 UI |
| `tests/test_answer_trace.py` | 校准与 chunk 公式用例 | 回归 |


#### 测试

- `pytest tests/test_answer_trace.py tests/test_api_phase4.py` 通过


遇到问题：

- Streamlit 列内 `chat_input` 无法稳定吸底 → 改为**页面级** `chat_input`。
- Info 原按钮详情沉在列表底 → 改为每文档旁 **expander**。
- 伪进度按产品决策取消，仅展示 **elapsed Xs**（线程刷新秒数）。
- Chunk 句子截断属 splitter 特性，本步不改算法；表格/OCR 留 Step3.6。
- Chat | Trace **双栏独立滚动**：CSS 限定失败后改为 **方案 B**——Trace 移入左侧 Sidebar，与主区 Chat 使用 Streamlit 原生分区滚动。
- 计时 **方案 A**：去掉后台线程刷新 UI，仅展示最终 `elapsed Xs`，消除 `NoSessionContext`。


下一阶段：

**等待指令后进入 Step3** — Conversation Memory

---

### Step2：Multi-format Document Loader

状态：完成


实现：

- 统一 `load_document()` 入口：类型检测 → 分发 Loader → 统一 `Document`
- 后续流程不变：Splitter → Embedding → Vector DB
- `IngestService.ingest_file()`；`ingest_pdf()` 保留为别名
- API `/upload`、Streamlit uploader 支持多格式
- `register_loader()` 预留 xlsx/html 等扩展


#### 新增 Loader

| 格式 | 模块 | 实现 |
| --- | --- | --- |
| pdf | `loaders/pdf_loader.py` | PDFPlumberLoader（既有） |
| docx | `loaders/docx_loader.py` | python-docx（段落+表格文本） |
| doc | `loaders/docx_loader.py` | win32com Word，或 LibreOffice→docx |
| pptx | `loaders/ppt_loader.py` | python-pptx（按 slide） |
| ppt | `loaders/ppt_loader.py` | win32com PowerPoint，或 LibreOffice→pptx |
| md / txt | `loaders/text_loader.py` | 多编码纯文本读取 |


#### 修改文件

| 文件 | 原因 |
| --- | --- |
| `src/ingestion/loaders/` | **新增** 包：registry + 各格式 Loader |
| `src/services/ingest_service.py` | `ingest_file` 统一入库 |
| `apps/api/main.py` | 多格式上传校验与接线 |
| `apps/web/streamlit_app.py` | uploader 类型扩展 |
| `requirements.txt` | python-docx / python-pptx |
| `tests/test_multi_format_loaders.py` | Loader 单测 |
| `tests/test_api_phase4.py` | 上传契约 |


#### 调用流程

```text
File Upload
  → detect suffix
  → LOADER_REGISTRY[suffix]
  → list[Document]
  → Text Splitter
  → Embedding
  → Chroma / Registry
```


#### 测试

- `pytest tests/test_multi_format_loaders.py tests/test_api_phase4.py`


遇到问题：

- 遗留 `.doc` / `.ppt`：优先 **Microsoft Office COM 显式另存**为 docx/pptx，失败再试 LibreOffice；API/UI 返回 `conversion` + `pipeline_steps`。
- 未做表格结构化序列化 / OCR（属 Step3.6）。


#### Step2 完善：显式 Convert 步骤（本轮）

| 文件 | 说明 |
| --- | --- |
| `src/ingestion/office_convert.py` | **新增** ppt→pptx / doc→docx；Office COM 优先 |
| `src/services/ingest_service.py` | 入库流水线含 convert → load → split → embed_index |
| `apps/api/main.py` | 响应带 `conversion` / `pipeline_steps` |
| `apps/web/streamlit_app.py` | 展示转换信息与 Pipeline expander |
| `requirements.txt` | Windows 增加 `pywin32` |
| `tests/test_office_convert.py` | 转换步骤单测（mock） |

流程：

```text
detect → convert(ppt→pptx via powerpoint_com|soffice) → load → split → embed_index
```


下一阶段：

**等待指令** — Step3.5 Query Rewrite / Hybrid

---

### Step3：Conversation Memory

状态：完成


实现：

- `src/memory/`：ConversationStore + 历史窗口（max_turns / max_chars）
- `QAService.ask(..., conversation_id=)`：写入用户/助手消息；Prompt 注入截断历史；检索用轻量 memory-aware query（近 2 轮用户问 + 当前问，非 LLM Rewrite）
- API `/chat` 接受并返回 `conversation_id` + `memory` 摘要
- Streamlit 绑定 session `conversation_id`；Clear chat 开启新会话
- 配置：`USE_CONVERSATION_MEMORY` / `MEMORY_MAX_TURNS` / `MEMORY_MAX_CHARS` / `CONVERSATION_STORE_PATH`


#### Memory 管理方案

| 机制 | 说明 |
| --- | --- |
| conversation_id | UUID；无则创建，有则续写 |
| 存储 | JSON 文件（默认 `chroma_db/conversations.json`） |
| 窗口 | 最近 `MEMORY_MAX_TURNS` 轮用户话轮 + `MEMORY_MAX_CHARS` 字符预算 |
| Prompt | 仅注入窗口历史；单条过长截断至 600 字 |
| 检索 | `build_retrieval_query`：当前问 + 最多 2 条近期用户问（非 LLM 改写） |
| 硬上限 | 磁盘侧最多保留约 `max_turns*6` 条消息，防无限增长 |


#### 修改文件

| 文件 | 作用 |
| --- | --- |
| `src/memory/*` | Memory 模块 |
| `src/services/qa_service.py` | 接线 Memory |
| `src/generation/prompts/templates.py` | history 参数 |
| `src/generation/schemas.py` / `apps/api/main.py` | conversation_id 契约 |
| `apps/web/streamlit_app.py` | UI 会话绑定 |
| `src/config/settings.py` · `.env.example` | 配置项 |
| `tests/test_conversation_memory.py` | 单测 |


下一阶段：

**等待指令** — Step4 Session 模型配置管理

---

### Step3.5：Query Rewrite / Hybrid

状态：完成


实现：

- 独立 `src/query_rewrite/`：规则 / LLM（`rules_llm`）改写；失败回退 Step3 `build_retrieval_query`
- 检索用改写问；**回答 Prompt 仍用用户原问**（+ Memory 历史）
- Hybrid：Dense + BM25 → RRF → Rerank；**`USE_BM25=false` 默认关闭**，演示可手动开
- 小语料 BM25 全 0 分时回退词重叠打分（避免 demo 空召回）
- Trace / API / UI：原问、改写问、rewrite_method、use_hybrid
- 配置：`USE_QUERY_REWRITE` / `QUERY_REWRITE_MODE` + 既有 `USE_BM25`


#### 调用流程

```text
Current Query (+ Memory)
  → Query Rewrite（llm/rules；失败 → memory concat）
  → Dense[/Hybrid if USE_BM25]
  → Rerank
  → Prompt(原问 + history) → LLM
```


#### 修改文件

| 文件 | 作用 |
| --- | --- |
| `src/query_rewrite/*` | **新增** Query Rewrite 模块 |
| `src/retrieval/hybrid.py` | Dense(+BM25) RRF；带 retrieval_score |
| `src/indexing/bm25_store.py` | 小语料 overlap 回退 |
| `src/services/qa_service.py` | Rewrite + Hybrid 接线 |
| `src/generation/trace.py` / `schemas.py` | Trace 字段 |
| `apps/api/main.py` · `apps/web/streamlit_app.py` | 契约透传 + Trace UI |
| `src/config/settings.py` · `.env.example` · `docker-compose.yml` | 开关 |
| `tests/test_query_rewrite_hybrid.py` | 单测 |


#### 测试

- `pytest tests/test_query_rewrite_hybrid.py tests/test_conversation_memory.py tests/test_answer_trace.py tests/test_router_and_postprocess.py tests/test_api_phase4.py` → **28 passed**


下一阶段：

**等待指令** — Step4 Session 模型配置管理

---

### Step3.6：表格序列化 + OCR

状态：完成


实现：

- `src/ingestion/tables.py`：行列 → Markdown 表
- PDF（pdfplumber）/ DOCX / PPTX：含表时输出 Markdown；不改 Loader 注册架构
- OCR 引擎 **A：pytesseract + 系统 Tesseract**；默认 `ENABLE_OCR=true`；缺依赖/二进制则跳过并打日志
- PDF 低文本页按需 OCR；PPTX 空页跳过并日志（不渲染 OCR）
- `pipeline_steps` 增加 `tables` / `ocr` 摘要
- 配置：`ENABLE_TABLE_SERIALIZATION` / `ENABLE_OCR` / `OCR_LANG` / `OCR_MIN_TEXT_CHARS` / `OCR_DPI`


#### 修改文件

| 文件 | 作用 |
| --- | --- |
| `src/ingestion/tables.py` | **新增** Markdown 表序列化 |
| `src/ingestion/ocr.py` | **新增** Tesseract OCR（可选、可跳过） |
| `src/ingestion/loaders/pdf_loader.py` | 表 + OCR |
| `src/ingestion/loaders/docx_loader.py` | Markdown 表 |
| `src/ingestion/loaders/ppt_loader.py` | 表格 shape → Markdown |
| `src/services/ingest_service.py` | pipeline_steps 聚合 |
| `src/config/settings.py` · `.env.example` · `docker-compose.yml` | 开关 |
| `requirements.txt` | Pillow / pytesseract |
| `tests/test_table_ocr.py` | 单测 |


#### 测试

- `pytest tests/test_table_ocr.py tests/test_multi_format_loaders.py tests/test_api_phase4.py` → **20 passed**


#### 运行注意

- 需本机安装 Tesseract（含 `chi_sim` 若用中文）；未安装时入库仍可继续，OCR 步骤记为 skipped


下一阶段：

（历史记录）其后已完成 Step4；当前下一个为 **Phase5 Evaluation**，再后 **Phase6**

---

### Step4：Session 模型配置管理

状态：完成


实现：

- `src/config/session_models.py`：Session 覆盖（LLM / Embedding / Reranker backend）；不写 `.env`；不含 Key
- `/chat` 接受 `llm_model` / `embed_model` / `reranker_backend`（或 `session_models`）
- `/session/models` GET/POST：读默认值、绑定 session embed
- `/upload` 可带 `embed_model` query
- Streamlit：可编辑模型；Apply / Reset；**Clear chat 保留覆盖**；浏览器刷新回 `.env` 默认
- Embedding 变更需重新上传文档才一致（UI 已提示）


#### Clear / Refresh 策略（本 Step 确认）

| 动作 | 模型覆盖 | 对话 Memory |
| --- | --- | --- |
| Clear chat | **保留** | 新 conversation_id |
| Reset to .env defaults | 清除覆盖 | 不变 |
| 浏览器刷新 | 丢失（回 `.env`） | 丢失 UI 会话 |


#### 测试

- `pytest tests/test_session_models.py tests/test_api_phase4.py tests/test_conversation_memory.py` → **14 passed**


下一阶段：

**等待指令** — Phase6 DashScope 云模型 + Session Key（或先做展示优化）

---

### Phase5：Evaluation

状态：完成


实现：

- 典型题集扩写：`data/eval/questions.json`（含 ground_truth / must_include，中英题）
- Recall@K：`src/eval/recall.py`
- RAGAS-style：`src/eval/ragas_lite.py`（faithfulness / answer_relevancy / context_precision）
- 统一 runner：`src/eval/runner.py` → Markdown + JSON 报告
- CLI：`python -m apps.cli.main eval`（`--skip-generation` 可只测召回）
- 操作说明：`docs/eval.md`


#### 测试

- `pytest tests/test_phase5_eval.py`（指标单测）


下一阶段：

**Phase6 = Future Work**（云 LLM/Embed + Session Key，秋招冲刺不强制）

---

### 文档 / 注释中文化（展示优化）

状态：完成


实现：

- **A 文档**：`docs/` 面向人的说明以中文为主（含 demo / ADR / eval / docker；消融报告章节标题中文化）
- **B README**：保持双语；中英区对齐现状（Step4 + Phase5 完成，Phase6=Future Work，Recall@5≈91.7%）
- **C 关键 docstring**：`src/services`、`src/eval`、`session_models`、`query_rewrite`、`ingestion`、`memory`、`router`、`generation/trace`、`apps/api`、`apps/cli`、`apps/web`
- **D UI**：Streamlit 侧栏 / 按钮 / Trace 面板文案中文化
- 评测报告 Markdown 模板改为中文（下次跑 `eval` 生效）
- **未改**：标识符、测试名、`.env`、业务行为；git 由用户自行处理


下一阶段：

**等待指令**

---

### Demo 截图（秋招展示）

状态：完成


实现：

- 真实 Streamlit UI 截图 4 张：`docs/demo/01_workspace_upload.png` … `04_eval_summary.png`
- README 中英文「功能展示」挂图；`docs/demo_script.md` 补充重截说明
- 可选脚本：`scripts/capture_demo_screenshots.py`（不改 RAG 主链；`playwright` 不写入 requirements）


下一阶段：

**等待指令**

---

### 冗余清理（秋招公开面）

状态：完成


实现：

- 删除过时 Phase2 检查清单 `docs/decision_log.md`（与 ADR/progress 三重叠且配置描述过时）
- 删除冗余脚本 `scripts/phase2_compare_rerank.py`（与 CLI `compare` / `generate_reranker_compare.py` 重叠）
- README 公开入口不再强链 `docs/progress.md`（进度账仍 git 跟踪，供本地开发）
- `RAG_ARCHITECTURE.md`：接入层改为 Streamlit；状态对齐 Phase5 / Phase6 Future Work


下一阶段：

**等待指令**
