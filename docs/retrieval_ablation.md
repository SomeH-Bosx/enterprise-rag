# 检索消融对比（Phase2 Reranker）

> 说明：正文 JSON 为历史跑批结果；章节标题已中文化。重新跑 `python -m apps.cli.main compare "..."` 可覆盖本文件。

问题: **What is the p95 latency SLO for Nebula Search Appliance?**

## 基线：仅 Dense Top-K（无重排）

```json
{
  "meta": {
    "mode": "naive",
    "use_reranker": false,
    "candidate_count": 5,
    "final_count": 5
  },
  "chunks": [
    {
      "chunk_id": "beta_product_spec_49680c9cbf799a3d::chunk::0",
      "doc_id": "beta_product_spec_49680c9cbf799a3d",
      "page": 0,
      "filename": "beta_product_spec.pdf",
      "snippet": "Beta Product Specification\nProduct name: Nebula Search Appliance.\nLatency SLO: p95 query latency under 200 milliseconds.\nSupported connectors: PDF, Markdown, Confluence.",
      "rerank_score": null,
      "rerank_rank": null
    },
    {
      "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::2",
      "doc_id": "enterprise_knowledge_mix_dbe74488888d5545",
      "page": 0,
      "filename": "enterprise_knowledge_mix.pdf",
      "snippet": "Cafeteria menu updates every Monday and includes vegetarian options.\nNebula Search Appliance latency SLO: p95 query latency under 200 milliseconds.\nNebula Search Appliance latency SLO: p95 query laten",
      "rerank_score": null,
      "rerank_rank": null
    },
    {
      "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::1",
      "doc_id": "enterprise_knowledge_mix_dbe74488888d5545",
      "page": 0,
      "filename": "enterprise_knowledge_mix.pdf",
      "snippet": "Cafeteria menu updates every Monday and includes vegetarian options.\nCafeteria menu updates every Monday and includes vegetarian options.\nCafeteria menu updates every Monday and includes vegetarian op",
      "rerank_score": null,
      "rerank_rank": null
    },
    {
      "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::5",
      "doc_id": "enterprise_knowledge_mix_dbe74488888d5545",
      "page": 0,
      "filename": "enterprise_knowledge_mix.pdf",
      "snippet": "Supported connectors for Nebula include PDF, Markdown, and Confluence.\nSupported connectors for Nebula include PDF, Markdown, and Confluence.\nSupported connectors for Nebula include PDF, Markdown, and",
      "rerank_score": null,
      "rerank_rank": null
    },
    {
      "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::4",
      "doc_id": "enterprise_knowledge_mix_dbe74488888d5545",
      "page": 0,
      "filename": "enterprise_knowledge_mix.pdf",
      "snippet": "Parking permits are required for all employee vehicles in lot B.\nParking permits are required for all employee vehicles in lot B.\nParking permits are required for all employee vehicles in lot B.\nParki",
      "rerank_score": null,
      "rerank_rank": null
    }
  ]
}
```

## Dense 宽召回 + 重排 → Top-N

```json
{
  "meta": {
    "mode": "dense_rerank",
    "use_reranker": true,
    "recall_k": 20,
    "top_n": 5,
    "candidate_count": 8,
    "final_count": 5
  },
  "chunks": [
    {
      "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::1",
      "doc_id": "enterprise_knowledge_mix_dbe74488888d5545",
      "page": 0,
      "filename": "enterprise_knowledge_mix.pdf",
      "snippet": "Cafeteria menu updates every Monday and includes vegetarian options.\nCafeteria menu updates every Monday and includes vegetarian options.\nCafeteria menu updates every Monday and includes vegetarian op",
      "rerank_score": 2.594088525727181,
      "rerank_rank": 1
    },
    {
      "chunk_id": "beta_product_spec_49680c9cbf799a3d::chunk::0",
      "doc_id": "beta_product_spec_49680c9cbf799a3d",
      "page": 0,
      "filename": "beta_product_spec.pdf",
      "snippet": "Beta Product Specification\nProduct name: Nebula Search Appliance.\nLatency SLO: p95 query latency under 200 milliseconds.\nSupported connectors: PDF, Markdown, Confluence.",
      "rerank_score": 2.57735026913407,
      "rerank_rank": 2
    },
    {
      "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::2",
      "doc_id": "enterprise_knowledge_mix_dbe74488888d5545",
      "page": 0,
      "filename": "enterprise_knowledge_mix.pdf",
      "snippet": "Cafeteria menu updates every Monday and includes vegetarian options.\nNebula Search Appliance latency SLO: p95 query latency under 200 milliseconds.\nNebula Search Appliance latency SLO: p95 query laten",
      "rerank_score": 2.4999999999583333,
      "rerank_rank": 3
    },
    {
      "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::5",
      "doc_id": "enterprise_knowledge_mix_dbe74488888d5545",
      "page": 0,
      "filename": "enterprise_knowledge_mix.pdf",
      "snippet": "Supported connectors for Nebula include PDF, Markdown, and Confluence.\nSupported connectors for Nebula include PDF, Markdown, and Confluence.\nSupported connectors for Nebula include PDF, Markdown, and",
      "rerank_score": 0.15430334993828237,
      "rerank_rank": 4
    },
    {
      "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::4",
      "doc_id": "enterprise_knowledge_mix_dbe74488888d5545",
      "page": 0,
      "filename": "enterprise_knowledge_mix.pdf",
      "snippet": "Parking permits are required for all employee vehicles in lot B.\nParking permits are required for all employee vehicles in lot B.\nParking permits are required for all employee vehicles in lot B.\nParki",
      "rerank_score": 0.10910894510609143,
      "rerank_rank": 5
    }
  ]
}
```
