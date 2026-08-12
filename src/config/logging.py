import logging
import uuid
from contextvars import ContextVar

import structlog

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def bind_request_id(request_id: str | None = None) -> str:
    rid = request_id or str(uuid.uuid4())
    request_id_var.set(rid)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def get_request_id() -> str:
    return request_id_var.get()


def setup_logging(level: str | None = None) -> None:
    """Unified JSON logging for API / services / router / retrieval."""
    level_name = (level or "INFO").upper()
    log_level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=log_level, format="%(message)s", force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str = "enterprise_rag"):
    return structlog.get_logger(name)
