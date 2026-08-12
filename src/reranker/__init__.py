"""Independent reranker package (Phase 2)."""

from src.reranker.base import BaseReranker
from src.reranker.dashscope_reranker import DashScopeReranker
from src.reranker.facade import Reranker
from src.reranker.lexical import LexicalReranker

# Backward-compatible name used by QAService / older imports.
CrossEncoderReranker = Reranker

__all__ = [
    "BaseReranker",
    "Reranker",
    "DashScopeReranker",
    "LexicalReranker",
    "CrossEncoderReranker",
]
