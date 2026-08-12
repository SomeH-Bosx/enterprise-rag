"""独立 Query Router 入口（Phase3）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.router.classifier import classify_query

logger = get_logger("query_router")

QueryTypeName = Literal["knowledge_query", "casual_chat"]


@dataclass(frozen=True)
class RouteResult:
    query_type: QueryTypeName
    method: str = "rules"
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QueryRouter:
    """Route user queries to knowledge RAG chain or casual LLM chat."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def route(self, query: str) -> RouteResult:
        if not self.settings.use_query_router:
            # Router disabled: preserve Phase1/2 behavior (always retrieve).
            result = RouteResult(
                query_type="knowledge_query",
                method="disabled",
                enabled=False,
            )
            logger.info("query_routed", **result.to_dict())
            return result

        query_type, method = classify_query(query, self.settings)
        result = RouteResult(query_type=query_type, method=method, enabled=True)
        logger.info("query_routed", **result.to_dict())
        return result


def route_query_intent(query: str, settings: Settings | None = None) -> dict[str, Any]:
    """Convenience API returning a structured dict: {"query_type": ...}."""
    result = QueryRouter(settings).route(query)
    return {"query_type": result.query_type, "method": result.method, "enabled": result.enabled}
