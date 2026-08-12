from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.settings import Settings, get_settings


class DocRegistry:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.path = Path(self.settings.doc_registry_path)
        self._docs: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._docs = data.get("documents", {})
        else:
            self._docs = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"documents": self._docs}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert(self, doc_id: str, source: str, chunk_count: int, filename: str) -> dict[str, Any]:
        record = {
            "doc_id": doc_id,
            "source": source,
            "filename": filename,
            "chunk_count": chunk_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._docs[doc_id] = record
        self.save()
        return record

    def delete(self, doc_id: str) -> bool:
        if doc_id not in self._docs:
            return False
        del self._docs[doc_id]
        self.save()
        return True

    def list_docs(self) -> list[dict[str, Any]]:
        return list(self._docs.values())

    def get(self, doc_id: str) -> dict[str, Any] | None:
        return self._docs.get(doc_id)

    def reset(self) -> None:
        self._docs = {}
        if self.path.exists():
            self.path.unlink()

    def count(self) -> int:
        return len(self._docs)
