import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import (
    MemoryStateStore,
    get_state_store,
)


def test_memory_state_store_flow():
    s = MemoryStateStore()

    assert s.get_last_history_id() is None
    s.set_last_history_id("100")
    assert s.get_last_history_id() == "100"

    assert not s.is_processed_history("h1")
    s.mark_processed_history("h1")
    assert s.is_processed_history("h1")

    assert not s.is_processed_message("m1")
    s.mark_processed_message("m1")
    assert s.is_processed_message("m1")


def test_get_state_store_default_memory(monkeypatch):
    # Ensure default returns memory store
    monkeypatch.delenv("PERSISTENCE_BACKEND", raising=False)
    cfg = {"settings": {}}
    store = get_state_store(cfg)
    assert isinstance(store, MemoryStateStore)


def test_get_state_store_selects_redis(monkeypatch):
    # Monkeypatch RedisStateStore to a dummy to avoid redis import
    import utils

    class DummyRedis:
        def __init__(self, url: str, ttl_days: int = 7, namespace: str = "salesdesk"):
            self.url = url
            self.ttl_days = ttl_days
            self.namespace = namespace

    monkeypatch.setenv("PERSISTENCE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(utils, "RedisStateStore", DummyRedis)

    store = get_state_store({"settings": {"persistence": {}}})
    assert isinstance(store, DummyRedis)
    assert store.url.endswith("/0")


def test_get_state_store_selects_postgres(monkeypatch):
    # Monkeypatch PostgresStateStore to a dummy to avoid psycopg2 import
    import utils

    class DummyPG:
        def __init__(self, dsn: str):
            self.dsn = dsn

    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setattr(utils, "PostgresStateStore", DummyPG)

    store = get_state_store({"settings": {"persistence": {}}})
    assert isinstance(store, DummyPG)
    assert store.dsn.startswith("postgresql://")

