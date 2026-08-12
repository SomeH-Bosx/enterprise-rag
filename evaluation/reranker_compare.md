# Reranker Compare (Phase2 DashScope Upgrade)

- Question: **What is the p95 latency SLO for Nebula Search Appliance?**
- DashScope mode: `live`
- Backend setting: `dashscope`
- Model: `gte-rerank-v2`

## Baseline

Retriever directly takes Top-K (no rerank).

- meta: `{"mode": "naive", "use_reranker": false, "candidate_count": 5, "final_count": 5}`

### Retrieved chunks

```json
[
  {
    "chunk_id": "beta_product_spec_49680c9cbf799a3d::chunk::0",
    "filename": "beta_product_spec.pdf",
    "rerank_score": null,
    "rerank_rank": null,
    "reranker": null,
    "snippet": "Beta Product Specification Product name: Nebula Search Appliance. Latency SLO: p95 query latency under 200 milliseconds. Supported connectors: PDF, Markdown, Confluence."
  },
  {
    "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::2",
    "filename": "enterprise_knowledge_mix.pdf",
    "rerank_score": null,
    "rerank_rank": null,
    "reranker": null,
    "snippet": "Cafeteria menu updates every Monday and includes vegetarian options. Nebula Search Appliance latency SLO: p95 query latency under 200 milliseconds. Nebula Search Appliance latency "
  },
  {
    "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::1",
    "filename": "enterprise_knowledge_mix.pdf",
    "rerank_score": null,
    "rerank_rank": null,
    "reranker": null,
    "snippet": "Cafeteria menu updates every Monday and includes vegetarian options. Cafeteria menu updates every Monday and includes vegetarian options. Cafeteria menu updates every Monday and in"
  },
  {
    "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::5",
    "filename": "enterprise_knowledge_mix.pdf",
    "rerank_score": null,
    "rerank_rank": null,
    "reranker": null,
    "snippet": "Supported connectors for Nebula include PDF, Markdown, and Confluence. Supported connectors for Nebula include PDF, Markdown, and Confluence. Supported connectors for Nebula includ"
  },
  {
    "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::4",
    "filename": "enterprise_knowledge_mix.pdf",
    "rerank_score": null,
    "rerank_rank": null,
    "reranker": null,
    "snippet": "Parking permits are required for all employee vehicles in lot B. Parking permits are required for all employee vehicles in lot B. Parking permits are required for all employee vehi"
  }
]
```

### Final answer

The p95 latency SLO for Nebula Search Appliance is under 200 milliseconds.

## Reranker

Retriever Top-20 → DashScope Reranker → Top-5 → LLM

- meta: `{"mode": "dense_rerank", "use_reranker": true, "recall_k": 20, "top_n": 5, "candidate_count": 8, "final_count": 5}`

### Retrieved chunks

```json
[
  {
    "chunk_id": "beta_product_spec_49680c9cbf799a3d::chunk::0",
    "filename": "beta_product_spec.pdf",
    "rerank_score": 0.9051482536448665,
    "rerank_rank": 1,
    "reranker": "dashscope",
    "snippet": "Beta Product Specification Product name: Nebula Search Appliance. Latency SLO: p95 query latency under 200 milliseconds. Supported connectors: PDF, Markdown, Confluence."
  },
  {
    "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::2",
    "filename": "enterprise_knowledge_mix.pdf",
    "rerank_score": 0.8072697905500292,
    "rerank_rank": 2,
    "reranker": "dashscope",
    "snippet": "Cafeteria menu updates every Monday and includes vegetarian options. Nebula Search Appliance latency SLO: p95 query latency under 200 milliseconds. Nebula Search Appliance latency "
  },
  {
    "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::1",
    "filename": "enterprise_knowledge_mix.pdf",
    "rerank_score": 0.49079675442512954,
    "rerank_rank": 3,
    "reranker": "dashscope",
    "snippet": "Cafeteria menu updates every Monday and includes vegetarian options. Cafeteria menu updates every Monday and includes vegetarian options. Cafeteria menu updates every Monday and in"
  },
  {
    "chunk_id": "enterprise_knowledge_mix_dbe74488888d5545::chunk::5",
    "filename": "enterprise_knowledge_mix.pdf",
    "rerank_score": 0.10464845587646363,
    "rerank_rank": 4,
    "reranker": "dashscope",
    "snippet": "Supported connectors for Nebula include PDF, Markdown, and Confluence. Supported connectors for Nebula include PDF, Markdown, and Confluence. Supported connectors for Nebula includ"
  },
  {
    "chunk_id": "acme_employee_handbook_b204440075c2ac5e::chunk::0",
    "filename": "acme_employee_handbook.pdf",
    "rerank_score": 0.005995403320697184,
    "rerank_rank": 5,
    "reranker": "dashscope",
    "snippet": "ACME Employee Handbook Paid leave policy: full-time employees receive 15 days annual leave. Remote work: employees may work remotely up to 3 days per week. Expense claims must be s"
  }
]
```

### Final answer

The p95 latency SLO for Nebula Search Appliance is under 200 milliseconds.

## Diff summary

- Baseline chunk_ids: `['beta_product_spec_49680c9cbf799a3d::chunk::0', 'enterprise_knowledge_mix_dbe74488888d5545::chunk::2', 'enterprise_knowledge_mix_dbe74488888d5545::chunk::1', 'enterprise_knowledge_mix_dbe74488888d5545::chunk::5', 'enterprise_knowledge_mix_dbe74488888d5545::chunk::4']`
- Rerank chunk_ids: `['beta_product_spec_49680c9cbf799a3d::chunk::0', 'enterprise_knowledge_mix_dbe74488888d5545::chunk::2', 'enterprise_knowledge_mix_dbe74488888d5545::chunk::1', 'enterprise_knowledge_mix_dbe74488888d5545::chunk::5', 'acme_employee_handbook_b204440075c2ac5e::chunk::0']`
- Order changed: **True**

## Typical case

For latency SLO questions, rerank should prioritize chunks containing `p95` / `latency` / `200 milliseconds` over cafeteria/parking noise.

## Notes

- If `DASHSCOPE_API_KEY` is empty, this report uses a mocked DashScope response so CI/local runs still produce a comparable artifact.
- Set a real key in `.env` and re-run for live semantic rerank scores.
