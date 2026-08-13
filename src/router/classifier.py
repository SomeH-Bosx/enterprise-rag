"""查询意图分类：规则优先，可选 LLM 回退。"""

from __future__ import annotations

import json
import re
from typing import Literal

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.generation.llm_gateway import invoke_text

logger = get_logger("query_classifier")

QueryType = Literal["knowledge_query", "casual_chat"]

_CASUAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(你好|您好|嗨|哈喽|hello|hi|hey)([\s,，!！.。?？]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(你是谁|你叫什么|你是什么|介绍一下你自己|who are you|what are you|"
        r"what'?s your name)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(谢谢|多谢|thank you|thanks|再见|拜拜|bye)([\s,，!！.。?？]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(早上好|下午好|晚上好|good\s*(morning|afternoon|evening)|how are you)"
        r"([\s,，!！.。?？]|$)",
        re.IGNORECASE,
    ),
)

_KNOWLEDGE_HINTS: tuple[str, ...] = (
    "政策",
    "年假",
    "假期",
    "规定",
    "制度",
    "手册",
    "公司",
    "文档",
    "合同",
    "流程",
    "标准",
    "slo",
    "latency",
    "handbook",
    "policy",
    "leave",
    "vacation",
    "how many",
    "what is",
    "根据",
    "查询",
    "说明",
)

_CLASSIFY_PROMPT = """你是企业 RAG 系统的查询分类器。只判断用户问题类型，不要回答问题本身。

可选类型（只能二选一）：
- knowledge_query: 需要检索企业知识库/文档才能回答（政策、制度、产品规格、事实查询等）
- casual_chat: 闲聊、问候、自我介绍、致谢等，不需要检索文档

用户问题：
{question}

只输出 JSON（不要 Markdown）：
{{"query_type":"knowledge_query"}}
或
{{"query_type":"casual_chat"}}
"""


def _normalize(query: str) -> str:
    return (query or "").strip()


def classify_by_rules(query: str) -> QueryType | None:
    """Return a confident rule decision, or None if ambiguous."""
    q = _normalize(query)
    if not q:
        return None

    lower = q.lower()
    has_knowledge_hint = any(hint in lower for hint in _KNOWLEDGE_HINTS)
    casual_hit = any(p.search(q) for p in _CASUAL_PATTERNS)

    if casual_hit and not has_knowledge_hint:
        return "casual_chat"
    if has_knowledge_hint:
        return "knowledge_query"
    # Short greeting-like utterances without knowledge keywords.
    if len(q) <= 12 and casual_hit:
        return "casual_chat"
    return None


def _parse_llm_label(raw: str) -> QueryType | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Strip optional markdown fences.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        label = str(data.get("query_type", "")).strip().lower()
    except json.JSONDecodeError:
        m = re.search(r"(knowledge_query|casual_chat)", text, re.IGNORECASE)
        label = m.group(1).lower() if m else ""
    if label in ("knowledge_query", "casual_chat"):
        return label  # type: ignore[return-value]
    return None


def classify_by_llm(query: str, settings: Settings | None = None) -> QueryType:
    cfg = settings or get_settings()
    prompt = _CLASSIFY_PROMPT.format(question=_normalize(query))
    raw = invoke_text(prompt, cfg)
    label = _parse_llm_label(raw)
    if label is None:
        logger.warning("classifier_llm_parse_failed", raw=raw[:200], fallback="knowledge_query")
        return "knowledge_query"
    return label


def classify_query(
    query: str,
    settings: Settings | None = None,
    *,
    prefer_llm: bool = False,
) -> tuple[QueryType, str]:
    """
    Classify query type.

    Returns:
        (query_type, method) where method is rules|llm|default
    """
    cfg = settings or get_settings()
    q = _normalize(query)

    if not prefer_llm:
        ruled = classify_by_rules(q)
        if ruled is not None:
            logger.info("query_classified", query_type=ruled, method="rules")
            return ruled, "rules"

    mode = (cfg.query_router_mode or "rules_llm").strip().lower()
    if mode in ("llm", "rules_llm", "hybrid"):
        try:
            label = classify_by_llm(q, cfg)
            logger.info("query_classified", query_type=label, method="llm")
            return label, "llm"
        except Exception as exc:  # noqa: BLE001
            logger.warning("classifier_llm_failed", error=str(exc), fallback="knowledge_query")

    # Safer default for enterprise RAG: retrieve unless clearly casual.
    logger.info("query_classified", query_type="knowledge_query", method="default")
    return "knowledge_query", "default"
