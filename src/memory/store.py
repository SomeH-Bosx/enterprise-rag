"""Conversation Memory — 轮次存储 + 有界历史窗口。

策略（Step3）：
- 按 conversation_id 持久化消息（JSON 文件存储）。
- 不把完整历史整段塞进 Prompt。
- 按最大轮次（user/assistant 对）与近似字符预算截窗。
- 检索侧用轻量记忆感知查询（当前问 + 近期用户轮），
  不做 LLM 查询改写（改写属 Step3.5）。
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.config.settings import Settings, get_settings

Role = Literal["user", "assistant"]


@dataclass
class Message:
    role: Role
    content: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        return cls(
            role=data.get("role") or "user",  # type: ignore[arg-type]
            content=str(data.get("content") or ""),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class Conversation:
    conversation_id: str
    messages: list[Message] = field(default_factory=list)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "messages": [m.to_dict() for m in self.messages],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Conversation":
        msgs = [Message.from_dict(m) for m in (data.get("messages") or []) if isinstance(m, dict)]
        return cls(
            conversation_id=str(data.get("conversation_id") or new_conversation_id()),
            messages=msgs,
            updated_at=str(data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )


def new_conversation_id() -> str:
    return uuid.uuid4().hex


def estimate_chars(text: str) -> int:
    return len(text or "")


def select_history_window(
    messages: list[Message],
    *,
    max_turns: int,
    max_chars: int,
) -> list[Message]:
    """
    Keep the most recent complete turns within turn + char budgets.

    A turn ≈ one user message (+ following assistant if present).
    Walk from the end; stop when adding the next older message would exceed budgets.
    """
    if not messages:
        return []
    max_turns = max(1, int(max_turns))
    max_chars = max(200, int(max_chars))

    selected_rev: list[Message] = []
    chars = 0
    # Count user messages as turns
    user_turns = 0
    for msg in reversed(messages):
        piece = estimate_chars(msg.content) + 16  # role overhead
        next_users = user_turns + (1 if msg.role == "user" else 0)
        if selected_rev and (chars + piece > max_chars or next_users > max_turns):
            break
        selected_rev.append(msg)
        chars += piece
        if msg.role == "user":
            user_turns = next_users
    selected = list(reversed(selected_rev))
    # Drop leading assistant-only orphan
    while selected and selected[0].role == "assistant":
        selected.pop(0)
    return selected


def format_history_for_prompt(messages: list[Message]) -> str:
    if not messages:
        return ""
    lines: list[str] = []
    for m in messages:
        label = "用户" if m.role == "user" else "助手"
        content = (m.content or "").strip()
        if not content:
            continue
        # Cap each message to avoid one long answer eating the budget again
        if len(content) > 600:
            content = content[:600] + "…"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def build_retrieval_query(current: str, history: list[Message], *, max_chars: int = 480) -> str:
    """
    Memory-aware retrieval query without LLM rewrite:
    prepend up to 2 recent user questions, then current question.
    """
    current = (current or "").strip()
    prior = [m.content.strip() for m in history if m.role == "user" and m.content.strip()]
    prior = prior[-2:]
    if not prior:
        return current
    # Avoid duplicating if user repeated the same text
    prior = [p for p in prior if p != current]
    if not prior:
        return current
    combined = "\n".join([*prior, current])
    if len(combined) <= max_chars:
        return combined
    # Prefer keeping the current question intact
    room = max_chars - len(current) - 1
    if room <= 0:
        return current[:max_chars]
    prefix = "\n".join(prior)[:room]
    return f"{prefix}\n{current}".strip()


class ConversationStore:
    """Thread-safe JSON-backed conversation store."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.path = Path(self.settings.conversation_store_path)
        self._lock = threading.RLock()
        self._data: dict[str, Conversation] = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                convs = raw.get("conversations") or {}
                self._data = {
                    cid: Conversation.from_dict(payload if isinstance(payload, dict) else {})
                    for cid, payload in convs.items()
                }
            else:
                self._data = {}

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "conversations": {cid: c.to_dict() for cid, c in self._data.items()}
            }
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def get_or_create(self, conversation_id: str | None) -> Conversation:
        with self._lock:
            cid = (conversation_id or "").strip() or new_conversation_id()
            if cid not in self._data:
                self._data[cid] = Conversation(conversation_id=cid)
                self.save()
            return self._data[cid]

    def get(self, conversation_id: str) -> Conversation | None:
        with self._lock:
            return self._data.get(conversation_id)

    def append(
        self,
        conversation_id: str,
        *,
        role: Role,
        content: str,
    ) -> Conversation:
        with self._lock:
            conv = self.get_or_create(conversation_id)
            conv.messages.append(Message(role=role, content=content))
            # Hard cap stored messages to avoid unbounded file growth
            max_keep = max(4, int(self.settings.memory_max_turns) * 2 * 3)
            if len(conv.messages) > max_keep:
                conv.messages = conv.messages[-max_keep:]
            conv.updated_at = datetime.now(timezone.utc).isoformat()
            self.save()
            return conv

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            if conversation_id in self._data:
                del self._data[conversation_id]
                self.save()

    def windowed_history(
        self,
        conversation_id: str,
        *,
        exclude_last_user: bool = False,
    ) -> list[Message]:
        """History for prompt/retrieval, already truncated."""
        conv = self.get(conversation_id)
        if not conv:
            return []
        messages = list(conv.messages)
        if exclude_last_user and messages and messages[-1].role == "user":
            messages = messages[:-1]
        return select_history_window(
            messages,
            max_turns=self.settings.memory_max_turns,
            max_chars=self.settings.memory_max_chars,
        )
