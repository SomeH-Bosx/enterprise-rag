"""Step3 Conversation Memory unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config.settings import Settings
from src.memory.store import (
    ConversationStore,
    Message,
    build_retrieval_query,
    format_history_for_prompt,
    select_history_window,
)
from src.services.qa_service import QAService


def test_select_history_window_limits_turns():
    msgs = []
    for i in range(10):
        msgs.append(Message(role="user", content=f"q{i}"))
        msgs.append(Message(role="assistant", content=f"a{i}"))
    window = select_history_window(msgs, max_turns=3, max_chars=5000)
    user_count = sum(1 for m in window if m.role == "user")
    assert user_count <= 3
    assert window[-1].content == "a9"


def test_select_history_window_limits_chars():
    msgs = [
        Message(role="user", content="u1 " + ("x" * 200)),
        Message(role="assistant", content="a1 " + ("y" * 200)),
        Message(role="user", content="u2 short"),
        Message(role="assistant", content="a2 short"),
    ]
    window = select_history_window(msgs, max_turns=10, max_chars=120)
    blob = format_history_for_prompt(window)
    assert len(blob) <= 120 + 50  # formatting labels add a bit; window itself char-gated
    assert "u2" in blob or "a2" in blob


def test_build_retrieval_query_includes_prior_user():
    history = [
        Message(role="user", content="公司年假几天？"),
        Message(role="assistant", content="15天"),
    ]
    q = build_retrieval_query("那病假呢？", history)
    assert "年假" in q
    assert "病假" in q


def test_conversation_store_persist(tmp_path: Path):
    settings = Settings(
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        USE_CONVERSATION_MEMORY=True,
        MEMORY_MAX_TURNS=4,
        MEMORY_MAX_CHARS=2000,
    )
    store = ConversationStore(settings)
    conv = store.get_or_create(None)
    cid = conv.conversation_id
    store.append(cid, role="user", content="hello")
    store.append(cid, role="assistant", content="hi")

    store2 = ConversationStore(settings)
    loaded = store2.get(cid)
    assert loaded is not None
    assert len(loaded.messages) == 2
    assert loaded.messages[0].content == "hello"


def test_qa_service_memory_roundtrip(tmp_path: Path):
    settings = Settings(
        CONVERSATION_STORE_PATH=str(tmp_path / "conv.json"),
        USE_CONVERSATION_MEMORY=True,
        USE_QUERY_ROUTER=True,
        MEMORY_MAX_TURNS=6,
        MEMORY_MAX_CHARS=3000,
    )
    store = ConversationStore(settings)
    qa = QAService(settings=settings, conversation_store=store)
    qa.query_router = MagicMock()
    route = MagicMock()
    route.query_type = "casual_chat"
    route.method = "rules"
    route.enabled = True
    qa.query_router.route.return_value = route

    with patch("src.services.qa_service.invoke_text", return_value="你好，我是助手。"):
        r1 = qa.ask("你好", structured=False, conversation_id=None)
    assert isinstance(r1, dict)
    cid = r1.get("conversation_id")
    assert cid
    assert store.get(cid) is not None
    assert len(store.get(cid).messages) == 2

    with patch("src.services.qa_service.invoke_text", return_value="还好，谢谢。") as mocked:
        r2 = qa.ask("我刚才说了什么？", structured=False, conversation_id=cid)
        prompt = mocked.call_args[0][0]
    assert r2["conversation_id"] == cid
    assert "你好" in prompt  # history injected
    assert len(store.get(cid).messages) == 4
