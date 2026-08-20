# RAG Pipeline 与核心模块（Phase5 定稿）

> 用途：理解整条数据流 + 面试口述地图。架构图见 [`RAG_ARCHITECTURE.md`](../RAG_ARCHITECTURE.md)。  
> **默认服务：** Hybrid `RECALL_TOP_N=20` → Reranker `TOP_K=5` → Ollama 生成。

---

## 1. 端到端 Pipeline（两条路径）

### 1.1 入库（离线 / 上传时）

```text
文件
  → Office 转换（旧 .doc/.ppt 等，可选）
  → Loader（pdf / docx / pptx / md / txt）
  → 表格 Markdown / OCR（可选）
  → Chunk（RecursiveCharacterTextSplitter）
  → Embedding（Ollama nomic-embed-text）
  → 写入 Chroma + BM25 Store + DocRegistry
```

**入口：** `IngestService`（`src/services/ingest_service.py`）← API `/upload`、CLI `ingest-dir`。

### 1.2 问答（在线，默认知识库）

```text
User Query
  → Query Router
       ├─ casual_chat →（可选 Memory）→ Ollama 直答（不检索）
       └─ knowledge_query
            →（可选）Query Rewrite     # 只改检索问，生成仍用原问
            → retrieve_candidates(k=20) # Dense@20 + BM25@20 → RRF → 截断 20
            → Reranker → Top-5
            → Prompt（原问 + 上下文 + 可选 Memory）
            → Ollama LLM
            → Answer + Sources + Trace
```

**入口：** `QAService.ask`（`src/services/qa_service.py`）← API `/chat`、Streamlit。

### 1.3 一句话口述（面试）

> 用户问题先经 Router：闲聊跳检索；知识问题可选改写后做 Hybrid 宽召回 20 条，Reranker 精排到 5 条，再用原问题 + 上下文让本地 LLM 生成，并带回引用与 Trace。

---

## 2. 核心模块地图

| 模块 | 路径 | 输入 → 输出 | 你要能说清的一点 |
| --- | --- | --- | --- |
| **Ingest** | `src/services/ingest_service.py` · `src/ingestion/` | 文件 → chunks 入双索引 | 多格式；切块后同时写 Chroma 与 BM25 |
| **Embeddings / Vector** | `src/indexing/embeddings.py` · `vectorstore.py` | text → vector；query → Top-N | Dense 近邻；距离可映射 Trace 相似度 |
| **BM25** | `src/indexing/bm25_store.py` | query → 稀疏 Top-N | 关键词互补；Hybrid 必需 |
| **Hybrid / RRF** | `src/retrieval/hybrid.py` | Dense 列表 + BM25 列表 → 融合排序 | 公式不变；输出截断到 `recall_top_n` |
| **Reranker** | `src/reranker/facade.py` 等 | (query, candidates) → Top-K | 默认 DashScope；失败回退 Lexical |
| **Router** | `src/router/` | query → knowledge / casual | 省掉闲聊上的无用检索 |
| **Rewrite** | `src/query_rewrite/` | 多轮语境 → 检索用问句 | **不改**最终回答用的原问 |
| **Memory** | `src/memory/` | conversation_id → 历史窗口 | Session 可关；评测时常关 |
| **Generation** | `src/generation/` | prompt → answer；+ Trace | Ollama；后处理校验页码等 |
| **QA 编排** | `src/services/qa_service.py` | 串起上面全部 | 真正的「产品主路径」 |
| **Eval** | `src/eval/` | 题集 → Recall / citation / latency | 公平 A/B；strict = `(filename,page)` |
| **API / UI** | `apps/api/` · `apps/web/` | HTTP / Streamlit | 不写死密钥；Session 可覆盖模式 |

---

## 3. 默认配置与 Phase5 结论（绑在一起记）

| 项 | 值 |
| --- | --- |
| `RETRIEVAL_MODE` | `hybrid` |
| `RECALL_TOP_N`（candidate_k） | `20` |
| `TOP_K`（rerank / 上下文条数） | `5` |
| `USE_RERANKER` | `true` |
| Generation | 开（`/chat` 走 LLM） |

**评测结论（记数字即可）：** Hybrid@10/20/30 的 Recall@5 都是 83.33%；Hybrid@20+Rerank 到 86.67%，strict citation 62.07%→75.86%。说明瓶颈在 **Top-5 排序**，不在再加宽召回。

---

## 4. 建议阅读顺序（约 1 小时）

1. 本文 + `RAG_ARCHITECTURE.md`（建立图景）  
2. `qa_service.py`：`ask` → `retrieve` / `retrieve_with_rerank`  
3. `hybrid.py`：`hybrid_retrieve` / `rrf_fuse`  
4. `reranker/facade.py`  
5. `ingest_service.py` 一条入库路径  
6. `docs/eval.md`（知道怎么证明有效）

---

## 5. 常见追问（短答）

- **为什么 Dual Index？** Dense 语义、BM25 关键词；RRF 融合比单路更稳。  
- **Rewrite 会不会改答案？** 不会；只影响检索 query。  
- **Rerank 挂了怎么办？** Facade 回退 Lexical，链路不断。  
- **Hit@5 是什么？** 本仓库里是 Recall@5 的别名，不是第二套指标。
