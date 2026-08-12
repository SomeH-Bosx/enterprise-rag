from __future__ import annotations

import hashlib
import shutil
import threading
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from src.config.logging import get_logger
from src.config.session_models import SessionModelOverrides
from src.config.settings import Settings, get_settings
from src.indexing.bm25_store import BM25Store
from src.indexing.doc_registry import DocRegistry
from src.indexing.vectorstore import VectorStoreManager
from src.ingestion.loaders import load_document
from src.ingestion.office_convert import prepare_for_load
from src.ingestion.splitters import split_documents
from src.services.exceptions import DocumentNotFoundError, IngestError

logger = get_logger("ingest")


def make_doc_id(path: Path) -> str:
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:16]
    stem = path.stem.replace(" ", "_")[:40]
    return f"{stem}_{digest}"


class IngestService:
    def __init__(
        self,
        settings: Settings | None = None,
        vector_store: VectorStoreManager | None = None,
        bm25_store: BM25Store | None = None,
        registry: DocRegistry | None = None,
    ):
        self.settings = settings or get_settings()
        self.vector_store = vector_store or VectorStoreManager(self.settings)
        self.bm25_store = bm25_store or BM25Store(self.settings)
        self.registry = registry or DocRegistry(self.settings)
        self._ingest_lock = threading.RLock()

    def ingest_file(
        self,
        path: str | Path,
        doc_id: str | None = None,
        model_overrides: SessionModelOverrides | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Unified ingest:
          detect → [convert legacy] → load → split → embed → vector DB

        Optional session embed_model override applies for this upload only
        (rebinds vector store embedding; does not write .env).
        """
        overrides = (
            model_overrides
            if isinstance(model_overrides, SessionModelOverrides)
            else SessionModelOverrides.from_mapping(model_overrides)
        )
        with self._ingest_lock:
            return self._ingest_file_impl(path, doc_id=doc_id, overrides=overrides)

    def _ingest_file_impl(
        self,
        path: str | Path,
        *,
        doc_id: str | None,
        overrides: SessionModelOverrides,
    ) -> dict[str, Any]:
        src = Path(path)
        if not src.exists():
            raise IngestError(f"File not found: {src}")

        effective = overrides.apply(self.settings)
        if overrides.embed_model and overrides.embed_model != self.vector_store.settings.embed_model:
            # Rebind store embedding for this session and keep it (do not write .env).
            self.vector_store.settings = self.vector_store.settings.model_copy(
                update={"embed_model": overrides.embed_model}
            )
            self.vector_store.refresh()
            logger.info(
                "session_embed_bound",
                embed_model=overrides.embed_model,
                note="re-ingest existing docs if they were embedded with another model",
            )

        result = self._ingest_body(src, doc_id=doc_id)
        result["session_models"] = overrides.to_public_dict(effective)
        return result

    def bind_session_embed(self, embed_model: str | None) -> dict[str, Any]:
        """Bind vector-store embedding to a session override (or restore default)."""
        with self._ingest_lock:
            target = (embed_model or "").strip() or self.settings.embed_model
            if target.lower().startswith("ollama:"):
                target = target.split(":", 1)[1].strip()
            prev = self.vector_store.settings.embed_model
            if target != prev:
                self.vector_store.settings = self.vector_store.settings.model_copy(
                    update={"embed_model": target}
                )
                self.vector_store.refresh()
            return {
                "embed_model": target,
                "previous": prev,
                "rebound": target != prev,
                "persisted_to_env": False,
            }

    def _ingest_body(self, src: Path, *, doc_id: str | None) -> dict[str, Any]:
        """Original ingest body (path already validated)."""
        cache_dir = Path(self.settings.upload_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / src.name
        if src.resolve() != cached.resolve():
            shutil.copy2(src, cached)

        original_type = cached.suffix.lower().lstrip(".") or "unknown"
        resolved_doc_id = doc_id or make_doc_id(cached)
        deleted = self.vector_store.delete_by_doc_id(resolved_doc_id)
        self.bm25_store.delete_by_doc_id(resolved_doc_id)

        # Explicit convert step for legacy Office formats (visible in API/UI)
        convert_dir = cache_dir / "_converted"
        conversion = prepare_for_load(cached, work_dir=convert_dir)
        pipeline_steps: list[dict[str, Any]] = list(conversion.steps)
        logger.info(
            "ingest_convert",
            filename=cached.name,
            converted=conversion.converted,
            engine=conversion.engine,
            from_type=conversion.from_type,
            to_type=conversion.to_type,
            elapsed_ms=conversion.elapsed_ms,
        )

        docs = load_document(conversion.load_path)
        pipeline_steps.append(
            {
                "step": "load",
                "status": "done",
                "loader_input": conversion.load_path.name,
                "original_file_type": original_type,
                "loaded_as": conversion.to_type if conversion.converted else original_type,
                "document_count": len(docs),
            }
        )

        # Step3.6: aggregate table / OCR signals from loader metadata (no RAG core change)
        table_docs = 0
        table_cells = 0
        ocr_applied = 0
        ocr_skipped = 0
        ocr_failed = 0
        ocr_statuses: list[str] = []
        for d in docs:
            meta = d.metadata or {}
            tc = int(meta.get("table_count") or 0)
            if tc > 0:
                table_docs += 1
                table_cells += tc
            status = str(meta.get("ocr_status") or "")
            if status:
                ocr_statuses.append(status)
            if status == "applied":
                ocr_applied += 1
            elif status == "failed":
                ocr_failed += 1
            elif status.startswith("skipped"):
                ocr_skipped += 1

        pipeline_steps.append(
            {
                "step": "tables",
                "status": "done" if self.settings.enable_table_serialization else "disabled",
                "enabled": bool(self.settings.enable_table_serialization),
                "docs_with_tables": table_docs,
                "table_count": table_cells,
            }
        )
        pipeline_steps.append(
            {
                "step": "ocr",
                "status": "done" if self.settings.enable_ocr else "disabled",
                "enabled": bool(self.settings.enable_ocr),
                "engine": "tesseract",
                "applied_pages": ocr_applied,
                "skipped_pages": ocr_skipped,
                "failed_pages": ocr_failed,
                "statuses": ocr_statuses[:40],
            }
        )
        logger.info(
            "ingest_enrichment",
            tables_enabled=self.settings.enable_table_serialization,
            table_count=table_cells,
            ocr_enabled=self.settings.enable_ocr,
            ocr_applied=ocr_applied,
            ocr_skipped=ocr_skipped,
            ocr_failed=ocr_failed,
        )

        split_docs = split_documents(docs, self.settings)
        if not split_docs:
            raise IngestError(f"No chunks produced from {original_type or 'document'}")
        pipeline_steps.append(
            {
                "step": "split",
                "status": "done",
                "chunk_count": len(split_docs),
            }
        )

        prepared: list[Document] = []
        ids: list[str] = []
        for i, doc in enumerate(split_docs):
            page = doc.metadata.get("page", 0)
            try:
                page_i = int(page)
            except (TypeError, ValueError):
                page_i = 0
            chunk_id = f"{resolved_doc_id}::chunk::{i}"
            meta = {
                "doc_id": resolved_doc_id,
                "source": str(cached),
                "filename": cached.name,
                "file_type": original_type,
                "page": page_i,
                "chunk_id": chunk_id,
            }
            if conversion.converted:
                meta["converted_from"] = conversion.from_type
                meta["converted_to"] = conversion.to_type
                meta["convert_engine"] = conversion.engine
            prepared.append(Document(page_content=doc.page_content, metadata=meta))
            ids.append(chunk_id)

        self.vector_store.add_documents(prepared, ids=ids)
        self.bm25_store.upsert_documents(prepared)
        pipeline_steps.append(
            {
                "step": "embed_index",
                "status": "done",
                "chunk_count": len(prepared),
                "replaced_chunks": deleted,
            }
        )

        record = self.registry.upsert(
            doc_id=resolved_doc_id,
            source=str(cached),
            chunk_count=len(prepared),
            filename=cached.name,
        )
        logger.info(
            "ingest_done",
            doc_id=resolved_doc_id,
            filename=cached.name,
            file_type=original_type,
            chunk_count=len(prepared),
            replaced_chunks=deleted,
            converted=conversion.converted,
            convert_engine=conversion.engine,
        )
        return {
            "doc_id": resolved_doc_id,
            "chunk_count": len(prepared),
            "filename": cached.name,
            "file_type": original_type,
            "replaced_chunks": deleted,
            "document": record,
            "conversion": conversion.to_dict(),
            "pipeline_steps": pipeline_steps,
        }

    def ingest_pdf(self, path: str | Path, doc_id: str | None = None) -> dict[str, Any]:
        """Backward-compatible alias for ingest_file."""
        return self.ingest_file(path, doc_id=doc_id)

    def delete_document(self, doc_id: str) -> dict[str, Any]:
        if not self.registry.get(doc_id):
            raise DocumentNotFoundError(doc_id)
        v_deleted = self.vector_store.delete_by_doc_id(doc_id)
        b_deleted = self.bm25_store.delete_by_doc_id(doc_id)
        self.registry.delete(doc_id)
        return {"doc_id": doc_id, "vector_deleted": v_deleted, "bm25_deleted": b_deleted}

    def list_documents(self) -> list[dict[str, Any]]:
        return self.registry.list_docs()

    def reset_all(self) -> dict[str, Any]:
        self.vector_store.reset()
        self.bm25_store.reset()
        self.registry.reset()
        cache = Path(self.settings.upload_cache_dir)
        if cache.exists():
            for f in cache.glob("*"):
                if f.is_file():
                    f.unlink()
            converted = cache / "_converted"
            if converted.exists():
                shutil.rmtree(converted, ignore_errors=True)
        return {"reset": True}
