# Architecture Decision Records

## ADR-1: Local-first models (Ollama)

**Decision**: Default LLM/Embedding to Ollama (`qwen2.5:7b`, `nomic-embed-text`).

**Why**: Enterprise demos and compliance narratives require data-not-leaving-host. Cloud providers remain possible later via a gateway abstraction, but local is the default path for this project.

## ADR-2: Hybrid retrieval (Dense + BM25 + RRF)

**Decision**: Recall with Chroma dense search and BM25, fuse with Reciprocal Rank Fusion, then cut to `TOP_K` after rerank.

**Why**: Dense retrieval misses exact tokens (policy numbers, product names). BM25 recovers lexical hits. RRF is robust without score calibration.

## ADR-3: CrossEncoder rerank instead of LLM rerank

**Decision**: Use `BAAI/bge-reranker-base` (sentence-transformers CrossEncoder). Do **not** call the LLM once per candidate.

**Why**: Project B's LLM-per-chunk rerank is accurate in contests but too slow/expensive for production. CrossEncoder gives most of the quality at far lower latency/cost.

## ADR-4: FastAPI core + thin Gradio

**Decision**: Business logic lives in services; FastAPI is the system boundary; Gradio only calls HTTP APIs.

**Why**: Resume-ready systems must be integrable. UI demos are not backends.

## ADR-5: Structured answers + citation validation

**Decision**: Chat returns JSON (`final_answer`, `reasoning_summary`, `relevant_pages`, `citations`) and drops hallucinated page numbers.

**Why**: Auditable outputs matter more than fluent prose in enterprise knowledge bases.

## ADR-6: Document-scoped upsert, not wipe-and-rebuild

**Decision**: Ingest upserts by `doc_id`; reset is an explicit operator action.

**Why**: Multi-document knowledge bases cannot survive Project A's full `rmtree` ingest pattern.
