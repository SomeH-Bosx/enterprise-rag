# 架构决策记录（ADR）

## ADR-1：本地优先模型（Ollama）

**决策**：默认 LLM / Embedding 使用 Ollama（如 `qwen2.5:7b`、`nomic-embed-text`）。

**原因**：企业演示与合规叙事需要「数据尽量不出本机」。云厂商可通过后续网关扩展（Phase6，见 README Future Work），但本项目默认走本地路径。

## ADR-2：Hybrid 检索（Dense + BM25 + RRF）

**决策**：Dense（Chroma）与 BM25 召回后用 Reciprocal Rank Fusion 融合，再经 Rerank 截断到 `TOP_K`。BM25 默认关闭，演示可开。

**原因**：纯向量检索容易漏精确词（制度数字、产品名）；BM25 补齐词法命中；RRF 无需复杂分值对齐。

## ADR-3：Reranker 优先语义 API，而非「每个候选调一次 LLM」

**决策**：默认 DashScope `gte-rerank-v2`；失败回退 Lexical；可选本地 CrossEncoder。

**原因**：对每个 chunk 调生成模型做重排成本高、延迟大，不适合产品演示主路径。

## ADR-4：FastAPI 为核心 + 薄 UI

**决策**：业务逻辑在 `services`；FastAPI 为系统边界；Streamlit / Gradio 只调 HTTP。

**原因**：可集成、可测试；UI 不能替代后端。

## ADR-5：可引用答案 + Trace

**决策**：产品接口返回 `answer` + `sources`，并附带 Answer Trace / 置信度（无密钥、无完整 Prompt 泄露）。

**原因**：企业知识库更看重可审计，而不是只有流畅文案。

## ADR-6：按文档 upsert，禁止默认整库清空

**决策**：入库按 `doc_id` 覆盖更新；整库 reset 必须显式操作。

**原因**：多文档知识库不能依赖「每次 ingest 删光重建」。

## ADR-7：Session 模型覆盖不写回 `.env`

**决策**：UI 可改 LLM / Embedding / Reranker backend，仅当前 session；Clear chat 保留覆盖；浏览器刷新回默认。API Key 不进 UI 持久化（Phase6 Future Work 另议）。

**原因**：演示灵活且避免密钥进仓库。
