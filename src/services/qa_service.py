from __future__ import annotations

import threading
import time
from typing import Any

from langchain_core.documents import Document

from src.config.logging import get_logger
from src.config.session_models import SessionModelOverrides
from src.config.settings import Settings, get_settings
from src.generation.llm_gateway import invoke_chat, invoke_text
from src.generation.postprocess import build_chat_answer, docs_to_citations
from src.generation.prompts.templates import (
    build_casual_prompt,
    build_context,
    build_simple_prompt,
    build_structured_prompt,
)
from src.generation.schemas import ChatAnswer
from src.generation.trace import build_answer_trace
from src.indexing.bm25_store import BM25Store
from src.indexing.doc_registry import DocRegistry
from src.indexing.vectorstore import VectorStoreManager
from src.memory import (
    ConversationStore,
    format_history_for_prompt,
)
from src.query_rewrite import QueryRewriter, RewriteResult
from src.reranker import CrossEncoderReranker
from src.retrieval.hybrid import hybrid_retrieve
from src.retrieval.reranker import dense_with_scores, naive_dense_only
from src.router import QueryRouter, RouteResult
from src.services.exceptions import EmptyQueryError, NoIndexError

logger = get_logger("qa")


class QAService:
    def __init__(
        self,
        settings: Settings | None = None,
        vector_store: VectorStoreManager | None = None,
        bm25_store: BM25Store | None = None,
        registry: DocRegistry | None = None,
        reranker: CrossEncoderReranker | None = None,
        query_router: QueryRouter | None = None,
        conversation_store: ConversationStore | None = None,
        query_rewriter: QueryRewriter | None = None,
    ):
        self.settings = settings or get_settings()
        self.vector_store = vector_store or VectorStoreManager(self.settings)
        self.bm25_store = bm25_store or BM25Store(self.settings)
        self.registry = registry or DocRegistry(self.settings)
        self.reranker = reranker or CrossEncoderReranker(self.settings)
        self.query_router = query_router or QueryRouter(self.settings)
        self.conversation_store = conversation_store or ConversationStore(self.settings)
        self.query_rewriter = query_rewriter or QueryRewriter(self.settings)
        self._ask_lock = threading.RLock()

    def _ensure_index(self) -> None:
        if self.registry.count() == 0 or self.vector_store.count() == 0:
            raise NoIndexError()

    def retrieve_dense(self, question: str, k: int | None = None) -> list[Document]:
        """Phase1/Phase2 shared vector recall. Does not change VectorStore core."""
        return naive_dense_only(
            question,
            self.vector_store,
            k=self.settings.top_k if k is None else k,
            doc_ids=None,
        )

    def retrieve_candidates(self, question: str, k: int | None = None) -> list[Document]:
        """
        Wide recall for knowledge path.
        Dense by default; Dense+BM25 RRF when USE_BM25=true (Step3.5, default off).
        """
        recall = self.settings.top_k if k is None else k
        use_hybrid = bool(self.settings.use_bm25)
        if use_hybrid:
            return hybrid_retrieve(
                question,
                self.vector_store,
                self.bm25_store,
                doc_ids=None,
                settings=self.settings,
                use_bm25=True,
                recall_top_n=recall,
            )
        return dense_with_scores(
            question,
            self.vector_store,
            k=recall,
            doc_ids=None,
        )

    def retrieve_dense_scored(self, question: str, k: int | None = None) -> list[Document]:
        """Dense recall with retrieval_score attached for Answer Trace / Confidence."""
        return dense_with_scores(
            question,
            self.vector_store,
            k=self.settings.top_k if k is None else k,
            doc_ids=None,
        )

    def retrieve_with_rerank(
        self,
        question: str,
        *,
        recall_k: int | None = None,
        top_n: int | None = None,
    ) -> tuple[list[Document], dict[str, Any]]:
        """
        Phase 2 / Step3.5 pipeline:
        Dense[/Hybrid] recall (Top-K / recall_top_n) -> Reranker -> Top-N (top_k)
        """
        recall = recall_k if recall_k is not None else self.settings.recall_top_n
        final_n = top_n if top_n is not None else self.settings.top_k
        use_hybrid = bool(self.settings.use_bm25)

        t0 = time.perf_counter()
        candidates = self.retrieve_candidates(question, k=recall)
        recall_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "retriever_done",
            recall_k=recall,
            candidate_count=len(candidates),
            use_hybrid=use_hybrid,
            elapsed_ms=round(recall_ms, 2),
        )

        t1 = time.perf_counter()
        ranked = self.reranker.rerank(question, candidates, top_n=final_n)
        rerank_ms = (time.perf_counter() - t1) * 1000
        top_scores = [
            d.metadata.get("rerank_score")
            for d in ranked[:3]
            if d.metadata.get("rerank_score") is not None
        ]
        logger.info(
            "reranker_done",
            top_n=final_n,
            final_count=len(ranked),
            top_scores=top_scores,
            elapsed_ms=round(rerank_ms, 2),
        )
        mode = "hybrid_rerank" if use_hybrid else "dense_rerank"
        meta = {
            "mode": mode,
            "use_reranker": True,
            "use_hybrid": use_hybrid,
            "recall_k": recall,
            "top_n": final_n,
            "candidate_count": len(candidates),
            "final_count": len(ranked),
            "recall_ms": round(recall_ms, 2),
            "rerank_ms": round(rerank_ms, 2),
            "candidates": candidates,
        }
        return ranked, meta

    def retrieve(
        self,
        question: str,
        *,
        use_reranker: bool | None = None,
        naive: bool = False,
    ) -> tuple[list[Document], dict[str, Any]]:
        """
        Public retrieve API.
        - naive / Phase1: dense Top-K only
        - Phase2/Step3.5: dense[/hybrid] recall -> rerank -> Top-N
        """
        enable_rerank = self.settings.use_reranker if use_reranker is None else use_reranker
        use_hybrid = bool(self.settings.use_bm25)
        if naive or not enable_rerank:
            t0 = time.perf_counter()
            # naive stays dense-only for Phase1 ablation; hybrid still available via non-naive
            docs = (
                self.retrieve_candidates(question, k=self.settings.top_k)
                if use_hybrid and not naive
                else self.retrieve_dense_scored(question, k=self.settings.top_k)
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            mode = "hybrid" if (use_hybrid and not naive) else "naive"
            logger.info(
                "retriever_done",
                mode=mode,
                candidate_count=len(docs),
                use_hybrid=use_hybrid and not naive,
                elapsed_ms=round(elapsed_ms, 2),
            )
            return docs, {
                "mode": mode,
                "use_reranker": False,
                "use_hybrid": use_hybrid and not naive,
                "recall_k": self.settings.top_k,
                "top_n": self.settings.top_k,
                "candidate_count": len(docs),
                "final_count": len(docs),
                "recall_ms": round(elapsed_ms, 2),
                "candidates": docs,
            }
        return self.retrieve_with_rerank(question)

    def _attach_trace(
        self,
        payload: dict[str, Any],
        *,
        route: RouteResult,
        answer_text: str,
        candidates: list[Document],
        ranked: list[Document],
        meta: dict[str, Any],
        retrieved: bool,
        rewrite: RewriteResult | None = None,
        original_query: str = "",
    ) -> dict[str, Any]:
        use_hybrid = bool(meta.get("use_hybrid", self.settings.use_bm25 and retrieved))
        rewrite_info = rewrite.to_dict() if rewrite else {
            "original_query": original_query,
            "rewritten_query": original_query,
            "method": "identity",
            "used_rewrite": False,
        }
        trace = build_answer_trace(
            query_type=route.query_type,
            route_method=route.method,
            mode=str(meta.get("mode") or payload.get("mode") or ""),
            retrieved=retrieved,
            answer=answer_text,
            candidates=candidates,
            ranked=ranked,
            recall_k=meta.get("recall_k") or meta.get("candidate_count"),
            top_n=meta.get("top_n") or meta.get("final_count"),
            use_reranker=bool(meta.get("use_reranker")),
            use_hybrid=use_hybrid,
            original_query=str(rewrite_info.get("original_query") or original_query),
            rewritten_query=str(rewrite_info.get("rewritten_query") or original_query),
            rewrite_method=str(rewrite_info.get("method") or "identity"),
            used_rewrite=bool(rewrite_info.get("used_rewrite")),
            reranker_backend=self.settings.reranker_backend,
            llm_model=self.settings.llm_model,
            embed_model=self.settings.embed_model,
            expected_sources=1,
        )
        payload["trace"] = trace
        payload["confidence"] = trace["confidence_percent"]
        payload["confidence_percent"] = trace["confidence_percent"]
        payload["confidence_level"] = trace["confidence_level"]
        payload["route"] = route.query_type
        payload["retrieved_docs"] = trace["retrieved_docs"]
        payload["reranked_docs"] = trace["reranked_docs"]
        payload["model"] = trace["model"]
        payload["original_query"] = trace.get("original_query")
        payload["rewritten_query"] = trace.get("rewritten_query")
        payload["rewrite_method"] = trace.get("rewrite_method")
        payload["use_hybrid"] = use_hybrid
        return payload

    def _ask_casual(
        self,
        question: str,
        route: RouteResult,
        structured: bool,
        *,
        history_text: str = "",
        rewrite: RewriteResult | None = None,
    ) -> ChatAnswer | dict[str, Any]:
        """Phase3 casual_chat: skip retriever/reranker, answer with LLM directly."""
        t0 = time.perf_counter()
        prompt = build_casual_prompt(question, history=history_text)
        text = invoke_text(prompt, self.settings)
        llm_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "qa_done",
            mode="casual_chat",
            query_type=route.query_type,
            route_method=route.method,
            use_reranker=False,
            retrieved=False,
            llm_ms=round(llm_ms, 2),
        )
        payload: dict[str, Any] = {
            "answer": text,
            "citations": [],
            "mode": "casual_chat",
            "query_type": route.query_type,
            "route_method": route.method,
            "use_reranker": False,
            "use_hybrid": False,
            "candidate_count": 0,
            "final_count": 0,
            "retrieved": False,
            "llm_ms": round(llm_ms, 2),
            "original_query": question,
            "rewritten_query": question,
            "rewrite_method": (rewrite.method if rewrite else "identity"),
        }
        self._attach_trace(
            payload,
            route=route,
            answer_text=text,
            candidates=[],
            ranked=[],
            meta={
                "mode": "casual_chat",
                "use_reranker": False,
                "use_hybrid": False,
                "recall_k": 0,
                "top_n": 0,
            },
            retrieved=False,
            rewrite=rewrite,
            original_query=question,
        )
        if structured:
            return ChatAnswer(
                final_answer=text,
                reasoning_summary="casual_chat: skipped retrieval",
                relevant_pages=[],
                citations=[],
                routed_doc_ids=[],
                route_reason=f"casual_chat:{route.method}",
            )
        return payload

    def ask(
        self,
        question: str,
        structured: bool = False,
        conversation_id: str | None = None,
        model_overrides: SessionModelOverrides | dict[str, Any] | None = None,
    ) -> ChatAnswer | dict[str, Any]:
        """
        Ask with Query Router + optional Memory + Query Rewrite (Step3.5)
        + optional session model overrides (Step4; not persisted to .env).
        """
        overrides = (
            model_overrides
            if isinstance(model_overrides, SessionModelOverrides)
            else SessionModelOverrides.from_mapping(model_overrides)
        )
        with self._ask_lock:
            return self._ask_with_optional_overrides(
                question,
                structured=structured,
                conversation_id=conversation_id,
                overrides=overrides,
            )

    def _ask_with_optional_overrides(
        self,
        question: str,
        *,
        structured: bool,
        conversation_id: str | None,
        overrides: SessionModelOverrides,
    ) -> ChatAnswer | dict[str, Any]:
        base_settings = self.settings
        base_reranker = self.reranker
        base_router = self.query_router
        base_rewriter = self.query_rewriter
        effective = overrides.apply(base_settings)
        swapped = effective is not base_settings
        if swapped:
            self.settings = effective
            self.reranker = CrossEncoderReranker(effective)
            self.query_router = QueryRouter(effective)
            self.query_rewriter = QueryRewriter(effective)
            if overrides.embed_model and overrides.embed_model != base_settings.embed_model:
                # Query embedding follows store binding; flag for clients.
                logger.info(
                    "session_embed_override_noted",
                    session_embed=overrides.embed_model,
                    store_embed=base_settings.embed_model,
                    note="chat retrieval uses vector store embedding; re-upload after embed change",
                )
            logger.info(
                "session_models_applied",
                llm_model=effective.llm_model,
                embed_model=effective.embed_model,
                reranker_backend=effective.reranker_backend,
            )
        try:
            result = self._ask_impl(
                question,
                structured=structured,
                conversation_id=conversation_id,
            )
            if isinstance(result, dict):
                result["session_models"] = overrides.to_public_dict(effective)
            return result
        finally:
            if swapped:
                self.settings = base_settings
                self.reranker = base_reranker
                self.query_router = base_router
                self.query_rewriter = base_rewriter

    def _ask_impl(
        self,
        question: str,
        structured: bool = False,
        conversation_id: str | None = None,
    ) -> ChatAnswer | dict[str, Any]:
        """
        Ask with Query Router + optional Memory + Query Rewrite (Step3.5):
        - knowledge_query → Rewrite → Dense[/Hybrid] → Rerank → Prompt(原问) → LLM
        - casual_chat → LLM directly (history in prompt; no retrieval rewrite)
        """
        started = time.perf_counter()
        q = (question or "").strip()
        if not q:
            raise EmptyQueryError()

        use_memory = bool(self.settings.use_conversation_memory)
        conv_id = (conversation_id or "").strip() if use_memory else ""
        history_msgs = []
        history_text = ""
        rewrite = RewriteResult(
            original_query=q,
            rewritten_query=q,
            method="identity",
            used_rewrite=False,
        )
        retrieval_query = q

        if use_memory:
            conv = self.conversation_store.get_or_create(conv_id or None)
            conv_id = conv.conversation_id
            # Append user turn first so store is durable even if generation fails later
            self.conversation_store.append(conv_id, role="user", content=q)
            history_msgs = self.conversation_store.windowed_history(
                conv_id,
                exclude_last_user=True,
            )
            history_text = format_history_for_prompt(history_msgs)
            logger.info(
                "memory_loaded",
                conversation_id=conv_id,
                history_turns=sum(1 for m in history_msgs if m.role == "user"),
                history_msgs=len(history_msgs),
            )

        logger.info(
            "qa_request",
            query_preview=q[:120],
            structured=structured,
            conversation_id=conv_id or None,
        )
        try:
            # Router uses current user utterance (intent of this turn)
            route = self.query_router.route(q)
            logger.info(
                "router_result",
                query_type=route.query_type,
                method=route.method,
                enabled=route.enabled,
            )
            if route.query_type == "casual_chat":
                result = self._ask_casual(
                    q,
                    route,
                    structured,
                    history_text=history_text,
                    rewrite=rewrite,
                )
                result = self._finalize_memory(result, conv_id=conv_id, answer_text=_answer_text(result))
                logger.info("qa_total", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
                return result

            # Step3.5: rewrite for retrieval only; answer prompt keeps original q
            rewrite = self.query_rewriter.rewrite(q, history_msgs)
            retrieval_query = rewrite.rewritten_query or q
            logger.info(
                "query_rewrite",
                method=rewrite.method,
                used_rewrite=rewrite.used_rewrite,
                original_preview=q[:80],
                rewritten_preview=retrieval_query[:120],
                use_hybrid=bool(self.settings.use_bm25),
            )

            self._ensure_index()
            retrieved, meta = self.retrieve(
                retrieval_query,
                use_reranker=self.settings.use_reranker,
            )
            candidates = list(meta.pop("candidates", retrieved) or [])
            context = build_context(retrieved)
            route_reason = f"{meta.get('mode', '')}|query_type={route.query_type}|method={route.method}"

            t_llm = time.perf_counter()
            if structured:
                messages = build_structured_prompt(context, q, history=history_text)
                raw = invoke_chat(messages, self.settings)
                llm_ms = (time.perf_counter() - t_llm) * 1000
                answer = build_chat_answer(
                    raw,
                    retrieved,
                    routed_doc_ids=[],
                    route_reason=route_reason,
                )
                logger.info(
                    "qa_done",
                    mode=meta.get("mode"),
                    query_type=route.query_type,
                    route_method=route.method,
                    candidate_count=meta.get("candidate_count"),
                    final_count=len(retrieved),
                    use_reranker=meta.get("use_reranker"),
                    use_hybrid=meta.get("use_hybrid"),
                    rewrite_method=rewrite.method,
                    llm_ms=round(llm_ms, 2),
                )
                logger.info("qa_total", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
                # structured path returns ChatAnswer; attach memory via wrapper dict if needed
                if use_memory and conv_id:
                    self.conversation_store.append(
                        conv_id,
                        role="assistant",
                        content=answer.final_answer,
                    )
                    # Keep ChatAnswer for structured consumers; conversation_id not on model
                    return answer
                return answer

            prompt = build_simple_prompt(context, q, history=history_text)
            text = invoke_text(prompt, self.settings)
            llm_ms = (time.perf_counter() - t_llm) * 1000
            logger.info(
                "qa_done",
                mode=meta.get("mode"),
                query_type=route.query_type,
                route_method=route.method,
                candidate_count=meta.get("candidate_count"),
                final_count=len(retrieved),
                use_reranker=meta.get("use_reranker"),
                use_hybrid=meta.get("use_hybrid"),
                rewrite_method=rewrite.method,
                llm_ms=round(llm_ms, 2),
            )
            logger.info("qa_total", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
            payload: dict[str, Any] = {
                "answer": text,
                "citations": [c.model_dump() for c in docs_to_citations(retrieved)],
                "mode": meta.get("mode"),
                "query_type": route.query_type,
                "route_method": route.method,
                "use_reranker": meta.get("use_reranker"),
                "use_hybrid": meta.get("use_hybrid"),
                "candidate_count": meta.get("candidate_count"),
                "final_count": meta.get("final_count"),
                "retrieved": True,
                "llm_ms": round(llm_ms, 2),
                "retrieval_query": retrieval_query,
                "original_query": q,
                "rewritten_query": retrieval_query,
                "rewrite_method": rewrite.method,
            }
            self._attach_trace(
                payload,
                route=route,
                answer_text=text,
                candidates=candidates,
                ranked=retrieved,
                meta=meta,
                retrieved=True,
                rewrite=rewrite,
                original_query=q,
            )
            return self._finalize_memory(payload, conv_id=conv_id, answer_text=text)
        except Exception:
            logger.exception("qa_failed", query_preview=q[:120], conversation_id=conv_id or None)
            raise

    def _finalize_memory(
        self,
        result: ChatAnswer | dict[str, Any],
        *,
        conv_id: str,
        answer_text: str,
    ) -> ChatAnswer | dict[str, Any]:
        if not self.settings.use_conversation_memory or not conv_id:
            return result
        if answer_text:
            self.conversation_store.append(conv_id, role="assistant", content=answer_text)
        if isinstance(result, dict):
            result["conversation_id"] = conv_id
            result["memory"] = {
                "enabled": True,
                "max_turns": self.settings.memory_max_turns,
                "max_chars": self.settings.memory_max_chars,
                "stored_messages": len(
                    (self.conversation_store.get(conv_id).messages if self.conversation_store.get(conv_id) else [])
                ),
            }
        return result

    def compare_rerank(self, question: str) -> dict[str, Any]:
        """Ablation helper: dense-only Top-K vs dense-recall + rerank Top-N."""
        self._ensure_index()
        baseline_docs, baseline_meta = self.retrieve(question, use_reranker=False, naive=True)
        rerank_docs, rerank_meta = self.retrieve_with_rerank(question)
        baseline_meta = {k: v for k, v in baseline_meta.items() if k != "candidates"}
        rerank_meta = {k: v for k, v in rerank_meta.items() if k != "candidates"}

        def summarize(docs: list[Document]) -> list[dict[str, Any]]:
            rows = []
            for d in docs:
                rows.append(
                    {
                        "chunk_id": d.metadata.get("chunk_id"),
                        "doc_id": d.metadata.get("doc_id"),
                        "page": d.metadata.get("page"),
                        "filename": d.metadata.get("filename"),
                        "snippet": (d.page_content or "")[:200],
                        "rerank_score": d.metadata.get("rerank_score"),
                        "rerank_rank": d.metadata.get("rerank_rank"),
                        "retrieval_score": d.metadata.get("retrieval_score"),
                    }
                )
            return rows

        return {
            "question": question,
            "baseline_dense": {
                "meta": baseline_meta,
                "chunks": summarize(baseline_docs),
            },
            "dense_plus_rerank": {
                "meta": rerank_meta,
                "chunks": summarize(rerank_docs),
            },
        }


def _answer_text(result: ChatAnswer | dict[str, Any]) -> str:
    if isinstance(result, ChatAnswer):
        return result.final_answer
    return str(result.get("answer") or result.get("final_answer") or "")
