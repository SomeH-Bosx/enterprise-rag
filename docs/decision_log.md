# Phase2 完成情况检查（只读，未改代码）

对照 [`development_plan.md`](enterprise-rag/docs/development_plan.md) Phase2：目标是「向量召回有噪声 → 加 Reranker → Top20→Rerank→Top5→LLM」，验收是「对比加入 reranker 前后」。

---

## 1. Phase2 已经完成的功能

| 功能 | 状态 |
| --- | --- |
| 独立 Reranker 模块（与 VectorStore 解耦） | 已完成 |
| Dense 宽召回 `RECALL_TOP_N=20` | 已完成 |
| Rerank 后截断 `TOP_K=5` | 已完成 |
| 接入问答：`ask()` 在 `USE_RERANKER=true` 时走 `dense_rerank` | 已完成 |
| 开关可回退 Phase1（`USE_RERANKER=false` / `naive`） | 已完成 |
| 前后对比：`compare_rerank` + `docs/retrieval_ablation.md` | 已完成（偏检索排序对比） |
| CrossEncoder 实现存在 + Lexical 离线回退 | 已完成 |
| 未越界做 Router / Agent / Docker / Eval | 符合要求 |

当前 `.env`：`USE_RERANKER=true`，`RERANKER_BACKEND=lexical`。

---

## 2. 当前项目目录结构变化（相对 Phase1）

**新增**
```text
src/reranker/
├── __init__.py
├── base.py
├── cross_encoder.py
└── lexical.py

scripts/phase2_compare_rerank.py
tests/test_reranker.py
data/samples/enterprise_knowledge_mix.pdf
docs/retrieval_ablation.md   # Phase2 对比产物
```

**有接线改动、但非新目录**
- `src/services/qa_service.py`
- `src/retrieval/reranker.py`（兼容 shim）
- `src/config/settings.py`、`.env` / `.env.example`
- `apps/api/main.py`、`apps/cli/main.py`（对比入口）
- `docs/progress.md`

**未改核心**
- `src/indexing/vectorstore.py` 的 similarity 逻辑仍为 Dense Retriever 核心

---

## 3. Reranker 模块所在文件

| 角色 | 路径 |
| --- | --- |
| 包入口 | `src/reranker/__init__.py` |
| 抽象基类 | `src/reranker/base.py` |
| CrossEncoder 实现 | `src/reranker/cross_encoder.py` |
| Lexical 回退实现 | `src/reranker/lexical.py` |
| 旧路径兼容转发 | `src/retrieval/reranker.py` |
| 编排调用点 | `src/services/qa_service.py` → `retrieve_with_rerank()` |

---

## 4. 当前完整 RAG 调用链（含 Reranker）

```text
PDF
  → Loader → Splitter → Embedding → Chroma（Phase1，仍保持）

Question
  → Embedding(query)
  → Vector Retriever：similarity_search(k=RECALL_TOP_N=20)
  → Reranker.rerank(...)
  → 取 Top-N（TOP_K=5）
  → build_context + Prompt
  → Ollama LLM
  → Answer
```

入口：`QAService.ask()` → `retrieve(use_reranker=True)` → `retrieve_with_rerank()`。

---

## 5. Retriever 和 Reranker 之间的数据流

```text
Retriever 输出
  List[Document] 候选（宽召回，最多 20）
      │
      │  每个 Document: page_content + metadata(doc_id/page/chunk_id/...)
      ▼
Reranker 输入
  (query: str, documents: List[Document], top_n: int)
      │
      │  对每个 (query, chunk) 打分 → 排序 → 截断
      ▼
Reranker 输出
  List[Document]（长度 ≤ TOP_K=5）
  metadata 增加：rerank_score / rerank_rank / reranker
      │
      ▼
LLM Context
```

边界清晰：Retriever 只负责召回；Reranker 不读写向量库，只重排候选。

---

## 6. Reranker 解决了什么问题

- **问题**：纯向量 Top-K 会把语义相近但无关/噪声 chunk 送进 Prompt（计划原文：召回存在噪声）。
- **做法**：先宽召回，再用重排模型/词法分把更相关的块顶到前面，只把 Top-N 交给 LLM。
- **效果证据**：已有 `retrieval_ablation.md` 的 baseline vs dense+rerank 排序对比；端到端曾跑通 latency SLO 问答。

---

## 7. 是否满足进入 Phase3 的条件

**总体：可以进入 Phase3（Query Router），但有以下问题需你知情。**

### 发现的问题（只指出，不改代码）

1. **验收口径略弱于计划原文**  
   计划写的是「对比加入 reranker 前后的**回答质量**」；当前主要产物是**检索排序**对比（`retrieval_ablation.md`），缺少系统化的「同一题、开关 rerank、两边最终答案对照表」。

2. **当前默认不是 CrossEncoder**  
   `.env` 为 `RERANKER_BACKEND=lexical`（因 HuggingFace 下载失败）。架构支持 CrossEncoder，但本机默认未跑通目标模型 `bge-reranker-base`。

3. **消融对比不完全同条件**  
   baseline dense 用 `TOP_K=5` 直接召回；rerank 路径先召回最多 20 再截断到 5。对比的是「Phase1 路径 vs Phase2 路径」，不是「同一 20 候选集有无 rerank」的严格消融。

4. **Lexical 重排能力有限**  
   适合离线联调；对语义噪声的抑制弱于 CrossEncoder，简历/演示叙事需说明当前 backend。

---

**结论**：Phase2 目标链路（Top20 → Rerank → Top5 → LLM）与独立模块化已落地，Phase1 能力未破坏；在接受上述 4 点限制的前提下，**满足进入 Phase3 的条件**。

等你确认后，再开始 Phase3。