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
