"""Session-scoped model overrides (Step4).

Defaults still come from `.env` / Settings. Overrides never write back to disk
and must not carry API keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config.settings import Settings

ALLOWED_RERANKER_BACKENDS = frozenset(
    {"dashscope", "lexical", "cross_encoder", "auto"}
)


@dataclass
class SessionModelOverrides:
    llm_model: str | None = None
    embed_model: str | None = None
    reranker_backend: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "SessionModelOverrides":
        if not data:
            return cls()
        backend = data.get("reranker_backend")
        if backend is not None:
            backend = str(backend).strip().lower() or None
            if backend and backend not in ALLOWED_RERANKER_BACKENDS:
                backend = None
        return cls(
            llm_model=_clean(data.get("llm_model")),
            embed_model=_clean(data.get("embed_model")),
            reranker_backend=backend,
        )

    def has_any(self) -> bool:
        return bool(self.llm_model or self.embed_model or self.reranker_backend)

    def apply(self, base: Settings) -> Settings:
        """Return a copy of Settings with non-empty overrides applied."""
        updates: dict[str, Any] = {}
        if self.llm_model:
            updates["llm_model"] = self.llm_model
        if self.embed_model:
            updates["embed_model"] = self.embed_model
        if self.reranker_backend:
            updates["reranker_backend"] = self.reranker_backend
        if not updates:
            return base
        return base.model_copy(update=updates)

    def to_public_dict(self, effective: Settings | None = None) -> dict[str, Any]:
        """Safe fields for API/UI (no secrets)."""
        payload = {
            "llm_model": self.llm_model,
            "embed_model": self.embed_model,
            "reranker_backend": self.reranker_backend,
            "overridden": self.has_any(),
        }
        if effective is not None:
            payload["effective"] = {
                "llm_model": effective.llm_model,
                "embed_model": effective.embed_model,
                "reranker_backend": effective.reranker_backend,
            }
        return payload


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    # Strip accidental "Ollama:" UI prefix
    if text.lower().startswith("ollama:"):
        text = text.split(":", 1)[1].strip()
    return text or None


def defaults_from_settings(settings: Settings) -> dict[str, str]:
    return {
        "llm_model": settings.llm_model,
        "embed_model": settings.embed_model,
        "reranker_backend": settings.reranker_backend,
    }
