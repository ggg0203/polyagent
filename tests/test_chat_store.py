"""Tests for ChatStore — cross-session chat memory."""

import os
import tempfile

from polyagent.core.types import Message, Role
from polyagent.persistence.chat_store import ChatStore


def _make_store() -> ChatStore:
    """Create an isolated ChatStore backed by a temp db file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = ChatStore(db_path=path)
    # Stash path so we can clean up later
    store._db_path = path
    return store


def _cleanup(store: ChatStore) -> None:
    store.close()
    if hasattr(store, "_db_path") and os.path.exists(store._db_path):
        os.unlink(store._db_path)


def test_save_and_load_roundtrip() -> None:
    store = _make_store()
    try:
        msgs = [
            Message(role=Role.USER, content="你好"),
            Message(role=Role.ASSISTANT, content="你好呀！"),
        ]
        store.save_messages(msgs, "test_mode")

        loaded = store.load_last_session("test_mode")
        assert len(loaded) == 2
        assert loaded[0].role == Role.USER
        assert loaded[0].content == "你好"
        assert loaded[1].role == Role.ASSISTANT
        assert loaded[1].content == "你好呀！"
    finally:
        _cleanup(store)


def test_system_messages_excluded_from_save() -> None:
    store = _make_store()
    try:
        msgs = [
            Message(role=Role.SYSTEM, content="you are a bot"),
            Message(role=Role.USER, content="hi"),
        ]
        store.save_messages(msgs, "test_mode2")

        loaded = store.load_last_session("test_mode2")
        assert len(loaded) == 1
        assert loaded[0].role == Role.USER
    finally:
        _cleanup(store)


def test_empty_history_returns_empty_list() -> None:
    store = _make_store()
    try:
        loaded = store.load_last_session("nonexistent_mode")
        assert loaded == []
    finally:
        _cleanup(store)
