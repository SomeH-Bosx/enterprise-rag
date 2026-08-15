"""Session 级模型覆盖（Step4）。

默认仍来自 `.env` / Settings；覆盖不回写磁盘，且不得携带 API Key。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config.settings import Settings
from src.retrieval.hybrid import ALLOWED_RETRIEVAL_MODES, normalize_retrieval_mode

ALLOWED_RERANKER_BACKENDS = frozenset(
    {"dashscope", "lexical", "cross_encoder", "auto"}
)


def _parse_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


@dataclass
class SessionModelOverrides:
    llm_model: str | None = None
    embed_model: str | None = None
    reranker_backend: str | None = None
    retrieval_mode: str | None = None
    use_conversation_memory: bool | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "SessionModelOverrides":
        if not data:
            return cls()
        backend = data.get("reranker_backend")
        if backend is not None:
            backend = str(backend).strip().lower() or None
            if backend and backend not in ALLOWED_RERANKER_BACKENDS:
                backend = None
        mode_raw = data.get("retrieval_mode")
        mode: str | None = None
        if mode_raw is not None:
            cleaned = str(mode_raw).strip().lower()
            if cleaned in ALLOWED_RETRIEVAL_MODES:
                mode = cleaned
        return cls(
            llm_model=_clean(data.get("llm_model")),
            embed_model=_clean(data.get("embed_model")),
            reranker_backend=backend,
            retrieval_mode=mode,
            use_conversation_memory=_parse_optional_bool(
                data.get("use_conversation_memory")
            ),
        )

    def has_any(self) -> bool:
        return bool(
            self.llm_model
            or self.embed_model
            or self.reranker_backend
            or self.retrieval_mode
            or self.use_conversation_memory is not None
        )

    def apply(self, base: Settings) -> Settings:
        """返回应用非空覆盖后的 Settings 副本。"""
        updates: dict[str, Any] = {}
        if self.llm_model:
            updates["llm_model"] = self.llm_model
        if self.embed_model:
            updates["embed_model"] = self.embed_model
        if self.reranker_backend:
            updates["reranker_backend"] = self.reranker_backend
        if self.retrieval_mode:
            updates["retrieval_mode"] = normalize_retrieval_mode(
                self.retrieval_mode, use_bm25_fallback=False
            )
        if self.use_conversation_memory is not None:
            updates["use_conversation_memory"] = bool(self.use_conversation_memory)
        if not updates:
            return base
        return base.model_copy(update=updates)

    def to_public_dict(self, effective: Settings | None = None) -> dict[str, Any]:
        """供 API/UI 使用的安全字段（不含密钥）。"""
        from src.retrieval.hybrid import resolve_retrieval_mode

        payload = {
            "llm_model": self.llm_model,
            "embed_model": self.embed_model,
            "reranker_backend": self.reranker_backend,
            "retrieval_mode": self.retrieval_mode,
            "use_conversation_memory": self.use_conversation_memory,
            "overridden": self.has_any(),
        }
        if effective is not None:
            payload["effective"] = {
                "llm_model": effective.llm_model,
                "embed_model": effective.embed_model,
                "reranker_backend": effective.reranker_backend,
                "retrieval_mode": resolve_retrieval_mode(effective),
                "use_conversation_memory": bool(effective.use_conversation_memory),
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


def defaults_from_settings(settings: Settings) -> dict[str, Any]:
    from src.retrieval.hybrid import resolve_retrieval_mode

    return {
        "llm_model": settings.llm_model,
        "embed_model": settings.embed_model,
        "reranker_backend": settings.reranker_backend,
        "retrieval_mode": resolve_retrieval_mode(settings),
        "use_conversation_memory": bool(settings.use_conversation_memory),
    }
