"""Query Rewrite：为检索改写查询；生成答案仍使用用户原问。

流水线角色（Step3.5）：
  当前问 (+ Memory) → 改写 → Dense[/Hybrid] → 重排 → Prompt(原问) → LLM

改写失败 / 关闭时回退：
  Step3 记忆感知拼接（`build_retrieval_query`）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from src.config.logging import get_logger
from src.config.settings import Settings, get_settings
from src.generation.llm_gateway import invoke_text
from src.memory.store import Message, build_retrieval_query, format_history_for_prompt

logger = get_logger("query_rewrite")

RewriteMethod = Literal[
    "disabled",
    "identity",
    "rules",
    "llm",
    "memory_fallback",
]


@dataclass
class RewriteResult:
    original_query: str
    rewritten_query: str
    method: RewriteMethod
    used_rewrite: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "method": self.method,
            "used_rewrite": self.used_rewrite,
        }


_FOLLOWUP_HINTS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(那|那么|还有|另外|以及|同样|继续|关于这个|这个呢|那个呢)",
    ),
    re.compile(
        r"(呢\s*[?？]?$|怎么样|如何呢|多少呢|几天|几号)",
    ),
    re.compile(
        r"^(what about|how about|and the|also|same for)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(it|that|this|they|those)\b",
        re.IGNORECASE,
    ),
)

_REWRITE_PROMPT = """你是企业 RAG 检索查询改写器。根据对话历史，把当前用户问题改写成一条独立、完整、适合向量检索的查询。

规则：
1. 只输出改写后的查询文本，不要解释、不要 Markdown、不要引号包裹整句。
2. 补全指代（这/那/它/呢）与省略的主题，使单看改写问也能检索。
3. 不要编造文档中不存在的实体；不确定时保留原问题关键词。
4. 使用与用户相同的主要语言（中文或英文）。
5. 改写问应简短（通常不超过 80 字）。

对话历史：
{history}

当前用户问题：
{question}

改写后的检索查询：
"""


def _normalize(text: str) -> str:
    return (text or "").strip()


def _looks_like_followup(query: str) -> bool:
    q = _normalize(query)
    if not q:
        return False
    if len(q) <= 24 and any(p.search(q) for p in _FOLLOWUP_HINTS):
        return True
    return any(p.search(q) for p in _FOLLOWUP_HINTS[:3])


def _rule_rewrite(current: str, history: list[Message]) -> str | None:
    """
    短追问的轻量规则改写：
    出现代词 /「那…呢」时，把最近一轮用户话题前置拼接。
    """
    current = _normalize(current)
    if not current or not history:
        return None
    if not _looks_like_followup(current):
        return None
    prior_users = [m.content.strip() for m in history if m.role == "user" and m.content.strip()]
    if not prior_users:
        return None
    last = prior_users[-1]
    if last == current:
        return None
    # Keep last prior question as topic anchor + current follow-up
    combined = f"{last} {current}".strip()
    if len(combined) > 200:
        combined = f"{last[:120]}… {current}".strip()
    return combined


def _parse_llm_rewrite(raw: str, original: str) -> str | None:
    text = _normalize(raw)
    if not text:
        return None
    # Strip accidental JSON / quotes / labels
    if text.startswith("{") and "rewritten" in text.lower():
        try:
            data = json.loads(text)
            for key in ("rewritten_query", "query", "rewrite"):
                if isinstance(data.get(key), str) and data[key].strip():
                    text = data[key].strip()
                    break
        except json.JSONDecodeError:
            pass
    text = text.strip().strip('"').strip("'")
    for prefix in ("改写后的检索查询：", "改写：", "Query:", "Rewritten:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
    # Reject empty / identical-noop when LLM echoed instructions
    if not text or len(text) > 400:
        return None
    if "对话历史" in text or "当前用户问题" in text:
        return None
    # Accept even if equal to original (still a valid rewrite method=llm)
    return text


class QueryRewriter:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def rewrite(
        self,
        question: str,
        history: list[Message] | None = None,
    ) -> RewriteResult:
        original = _normalize(question)
        history = history or []
        if not original:
            return RewriteResult(
                original_query="",
                rewritten_query="",
                method="identity",
                used_rewrite=False,
            )

        if not self.settings.use_query_rewrite:
            fallback = build_retrieval_query(original, history)
            method: RewriteMethod = (
                "memory_fallback" if fallback != original else "disabled"
            )
            return RewriteResult(
                original_query=original,
                rewritten_query=fallback,
                method=method if fallback != original else "disabled",
                used_rewrite=False,
            )

        mode = (self.settings.query_rewrite_mode or "rules_llm").strip().lower()

        # 1) Rules (optional first pass)
        if mode in ("rules", "rules_llm"):
            ruled = _rule_rewrite(original, history)
            if ruled and mode == "rules":
                logger.info(
                    "query_rewrite_done",
                    method="rules",
                    original_preview=original[:80],
                    rewritten_preview=ruled[:120],
                )
                return RewriteResult(
                    original_query=original,
                    rewritten_query=ruled,
                    method="rules",
                    used_rewrite=True,
                )
            # rules_llm: use rule result only when confident follow-up; else try LLM
            if ruled and mode == "rules_llm" and _looks_like_followup(original):
                # Prefer LLM when available; rule is soft hint via history in prompt.
                pass

        # 2) LLM rewrite
        if mode in ("llm", "rules_llm"):
            try:
                history_text = format_history_for_prompt(history) or "(无)"
                prompt = _REWRITE_PROMPT.format(
                    history=history_text,
                    question=original,
                )
                raw = invoke_text(prompt, self.settings)
                parsed = _parse_llm_rewrite(raw, original)
                if parsed:
                    logger.info(
                        "query_rewrite_done",
                        method="llm",
                        original_preview=original[:80],
                        rewritten_preview=parsed[:120],
                    )
                    return RewriteResult(
                        original_query=original,
                        rewritten_query=parsed,
                        method="llm",
                        used_rewrite=parsed != original,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("query_rewrite_llm_failed", error=str(exc))

        # 3) Rule fallback after LLM miss (rules_llm)
        if mode == "rules_llm":
            ruled = _rule_rewrite(original, history)
            if ruled:
                logger.info(
                    "query_rewrite_done",
                    method="rules",
                    original_preview=original[:80],
                    rewritten_preview=ruled[:120],
                )
                return RewriteResult(
                    original_query=original,
                    rewritten_query=ruled,
                    method="rules",
                    used_rewrite=True,
                )

        # 4) Memory concat fallback (Step3 light path)
        fallback = build_retrieval_query(original, history)
        logger.info(
            "query_rewrite_fallback",
            method="memory_fallback",
            original_preview=original[:80],
            rewritten_preview=fallback[:120],
        )
        return RewriteResult(
            original_query=original,
            rewritten_query=fallback,
            method="memory_fallback" if fallback != original else "identity",
            used_rewrite=False,
        )
