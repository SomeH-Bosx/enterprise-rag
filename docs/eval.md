# Phase5 Evaluation

目标：用可重复指标证明 RAG 有效（Recall + RAGAS-style + 典型题集）。

## 1. 准备样例索引

确保 Ollama 已启动，并已 pull 模型。然后入库样例 PDF：

```bash
cd /d/Carrer/Project/RAG/enterprise-rag
source .venv/Scripts/activate   # Windows Git Bash
# 或: .venv\Scripts\activate

python -m apps.cli.main ingest-dir data/samples
```

## 2. 跑完整评测（Recall + 生成 + RAGAS-style）

```bash
python -m apps.cli.main eval
```

默认：

- 题集：`data/eval/questions.json`
- Markdown 报告：`evaluation/phase5_report.md`
- JSON 报告：`evaluation/phase5_report.json`

终端会打印 `metrics` JSON，例如 `recall_at_k`、`ragas.faithfulness` 等。

## 3. 只测召回（更快，不调 LLM 生成）

```bash
python -m apps.cli.main eval --skip-generation
```

## 3.5 公平 Reranker 消融（Hybrid@20）

同一组 Dense@20 + BM25@20 候选上比较：A = RRF Top-5（无 rerank），B = Rerank Top-5。

```bash
python -m apps.cli.main eval --rerank-ablation --skip-generation
```

默认写出：

- `evaluation/phase5/recall_hybrid20.md` / `.json`（A）
- `evaluation/phase5/recall_hybrid20_rerank.md` / `.json`（B）

JSON `metrics` 记录实际配置：`retrieval_mode`、`recall_k`、`candidate_count`、`top_k`、`use_reranker`、`use_bm25`。两份报告每题带相同的 `candidate_chunk_ids`，用于确认候选集合一致。

耗时口径（不把整段消融墙钟时间同时写进 A/B）：

- `retrieve_ms_total` / `latency_hybrid20_ms`：Hybrid@20 retrieval total = `sum(retrieve_ms)`
- `rerank_ms_total`：Reranker total = `sum(rerank_ms)`
- A `elapsed_ms` = Hybrid@20 total latency
- B `elapsed_ms` / `latency_hybrid20_rerank_ms` = Hybrid@20 + Reranker total latency

引用指标：

- `citation_page_hit_rate`：loose page hit（仅页码是否出现在 Top-K）
- `strict_citation_page_hit_rate`：strict citation hit（`(filename, page)` 同时匹配；filename 规则与 Recall 相同，大小写不敏感子串）

**Hit@K 不是独立指标。** JSON 里的 `hit_at_k` 等于 `recall_at_k`（同一 Top-K 文档命中布尔值的别名）。最终报告只展示 Recall@K，避免重复。

延迟口径：

- retrieval latency = `sum(retrieve_ms)`
- rerank latency = `sum(rerank_ms)`（无 rerank 为 0）
- total latency = 二者之和（该报告的 `elapsed_ms`）
- 不包含 LLM generation
- candidate-k 循环前有一次 warmup retrieve，不计入
- Ollama embedding 预热与 DashScope rerank 网络会使 **毫秒数在不同次运行间波动**；质量指标（Recall / citation）在同一索引上可离线复现

限制（limitation）：题量 n=30；无 `expected_page_hint` 的题不进 citation 分母；docx 可能 `page=0`；Hybrid@k 宽度是独立 `retrieve_candidates(k)`，不是更大列表的前缀。

已有 JSON 可离线重算（不重新检索）：

```bash
python -c "from src.eval.runner import refresh_ablation_reports_from_json; refresh_ablation_reports_from_json()"
```

## 3.6 Candidate 宽度消融（Hybrid@10/20/30）

同一题集、只测召回。Hybrid@k 各自 `retrieve_candidates(k)`；Hybrid@20 + Reranker 复用 k=20 候选。结果写入新目录，不覆盖 3.5 的 JSON。

```bash
python -m apps.cli.main eval --candidate-k-ablation --skip-generation
```

默认写出 `evaluation/phase5/candidate_k/`：

- `hybrid10.md` / `.json`
- `hybrid20.md` / `.json`
- `hybrid30.md` / `.json`
- `hybrid20_rerank.md` / `.json`
- `summary.md` / `.json`

## 4. 自定义路径

```bash
python -m apps.cli.main eval \
  --questions data/eval/questions.json \
  --report evaluation/my_report.md \
  --json-out evaluation/my_report.json
```

## 5. 如何看结果

1. 打开 `evaluation/phase5_report.md`：Summary（Recall / RAGAS-style）+ 每题明细  
2. 或打开 `evaluation/phase5_report.json`：机器可读完整 rows  
3. 关注：
   - **Recall@K**：期望文档是否进 Top-K
   - **faithfulness**：答案词是否被上下文支撑
   - **answer_relevancy**：答案与问题/标准答案的相关度
   - **must_include_pass_rate**：关键数字/关键词是否出现在答案里

## 说明

- RAGAS-style 使用仓库内轻量实现（`src/eval/ragas_lite.py`），概念对齐 RAGAS，默认不强制安装重型 `ragas` 包，便于本地稳定复现。
- 评测会临时关闭 Conversation Memory，避免污染会话存储。
