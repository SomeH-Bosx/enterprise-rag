"""RAGAS-style 答案/上下文指标（Phase5）。

默认用轻量、少依赖的代理指标，无需安装完整 RAGAS。概念对应：

- faithfulness ≈ 答案 token 是否被检索上下文支持
- answer_relevancy ≈ 答案与问题 / ground_truth 的重叠
- context_precision ≈ 期望来源是否出现在检索集（召回命中的别名）
"""

from __future__ import annotations

import re
from typing import Any, Sequence

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def _overlap_ratio(numerator: set[str], denominator: set[str]) -> float:
    if not denominator:
        return 0.0
    return len(numerator & denominator) / float(len(denominator))


def faithfulness_score(answer: str, contexts: Sequence[str]) -> float:
    """答案 token 出现在拼接上下文中的比例。"""
    ans = tokenize(answer)
    ctx = tokenize("\n".join(contexts or []))
    if not ans:
        return 0.0
    return _overlap_ratio(ans & ctx, ans)


def answer_relevancy_score(answer: str, question: str, ground_truth: str | None = None) -> float:
    """答案 token 与问题（及可选 ground_truth）的重叠度。"""
    ans = tokenize(answer)
    ref = tokenize(question) | tokenize(ground_truth or "")
    if not ans or not ref:
        return 0.0
    return _overlap_ratio(ans & ref, ans)


def must_include_pass(answer: str, must_include: Sequence[str] | None) -> bool | None:
    if not must_include:
        return None
    text = (answer or "").lower()
    return all(str(x).lower() in text for x in must_include)


def score_row(
    *,
    answer: str,
    question: str,
    contexts: Sequence[str],
    ground_truth: str | None = None,
    must_include: Sequence[str] | None = None,
    context_hit: bool = False,
) -> dict[str, Any]:
    faith = faithfulness_score(answer, contexts)
    relev = answer_relevancy_score(answer, question, ground_truth)
    include_ok = must_include_pass(answer, must_include)
    return {
        "faithfulness": round(faith, 4),
        "answer_relevancy": round(relev, 4),
        "context_precision": 1.0 if context_hit else 0.0,
        "must_include_pass": include_ok,
    }


def aggregate_ragas_style(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "faithfulness": 0.0,
            "answer_relevancy": 0.0,
            "context_precision": 0.0,
            "must_include_pass_rate": None,
            "n": 0,
        }
    n = len(rows)
    faith = sum(float(r.get("faithfulness") or 0) for r in rows) / n
    relev = sum(float(r.get("answer_relevancy") or 0) for r in rows) / n
    ctx = sum(float(r.get("context_precision") or 0) for r in rows) / n
    include_vals = [r.get("must_include_pass") for r in rows if r.get("must_include_pass") is not None]
    include_rate = (
        sum(1 for v in include_vals if v) / len(include_vals) if include_vals else None
    )
    return {
        "faithfulness": round(faith, 4),
        "answer_relevancy": round(relev, 4),
        "context_precision": round(ctx, 4),
        "must_include_pass_rate": None if include_rate is None else round(include_rate, 4),
        "n": n,
        "backend": "ragas_lite",
    }
