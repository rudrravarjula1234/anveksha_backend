"""Shared pytest fixtures.

Tests run against an in-memory async stub of the Motor collection
(`FakeCollection`). This keeps `pytest` runs hermetic — no Mongo
container required. The repository layer talks only to the collection
interface, so swapping it for a fake is safe.
"""

from __future__ import annotations

import copy
import os
from typing import Any, AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

# Force DEBUG before app imports so dev-token auth is enabled.
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("MONGO_URI", "mongodb://test/anveksha")  # never actually dialled
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")


# ── In-memory collection stub ─────────────────────────────────────────────


class _ChainableCursor:
    def __init__(self, items: list[dict[str, Any]]):
        self._items = items

    def sort(self, *_args, **_kwargs) -> "_ChainableCursor":
        # No-op for tests — order doesn't matter for our assertions.
        return self

    def limit(self, n: int) -> "_ChainableCursor":
        self._items = self._items[:n]
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:  # noqa: ARG002
        return list(self._items)


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    """Mongo-flavoured equality: a scalar query value against an array
    field means 'array contains' (e.g. {"roles": "admin"})."""
    for k, v in query.items():
        actual = doc.get(k)
        if isinstance(actual, list) and not isinstance(v, list):
            if v not in actual:
                return False
        elif actual != v:
            return False
    return True


class FakeCollection:
    """Async-compatible drop-in covering the slice of pymongo we use.

    Documents are DEEP-copied on insert and on read — real Mongo
    round-trips through BSON, so callers can never share references with
    stored documents. Without this, in-place mutation of nested dicts
    would leak into module-level seed constants across tests.
    """

    def __init__(self) -> None:
        self._docs: list[dict[str, Any]] = []

    async def insert_one(self, doc: dict[str, Any]):
        # Mimic Mongo by stamping an internal _id ourselves.
        doc.setdefault("_id", f"oid_{len(self._docs)}")
        self._docs.append(copy.deepcopy(doc))

        class _R:
            inserted_id = doc["_id"]

        return _R()

    async def find_one(self, query: dict[str, Any]):
        for d in self._docs:
            if _matches(d, query):
                return copy.deepcopy(d)
        return None

    def find(self, query: dict[str, Any] | None = None):
        if query:
            items = [d for d in self._docs if _matches(d, query)]
        else:
            items = list(self._docs)
        return _ChainableCursor([copy.deepcopy(d) for d in items])

    async def find_one_and_update(self, query: dict[str, Any], update: dict[str, Any], **_kw):
        for d in self._docs:
            if _matches(d, query):
                d.update(copy.deepcopy(update.get("$set", {})))
                return copy.deepcopy(d)
        return None

    async def delete_one(self, query: dict[str, Any]):
        for i, d in enumerate(self._docs):
            if _matches(d, query):
                self._docs.pop(i)

                class _R:
                    deleted_count = 1

                return _R()

        class _R:
            deleted_count = 0

        return _R()

    async def create_index(self, *_args, **_kwargs):
        return None


class FakeDB:
    """Dict-backed registry — every named collection persists for the
    lifetime of the fixture, mirroring a real database handle."""

    def __init__(self) -> None:
        self._collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]

    def __getattr__(self, name: str) -> FakeCollection:
        # Attribute access (db.bots) delegates to item access (db["bots"]).
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    async def command(self, *_args, **_kwargs):
        return {"ok": 1}


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    """Swap the ACTIVE Mongo handle for the in-memory stub.

    We patch `mongo._state.db` (the value the real `get_database()` reads
    on every call) rather than the function itself — service modules bind
    `get_database` at import time, so replacing the function attribute
    would only affect modules imported after the patch. Patching the
    state keeps every reference live and gives each test a fresh DB.
    """
    from app.db import mongo

    db = FakeDB()
    monkeypatch.setattr(mongo._state, "db", db)
    return db


@pytest.fixture
async def client(fake_db: FakeDB) -> AsyncIterator[AsyncClient]:  # noqa: ARG001
    """ASGI test client.

    httpx's ASGITransport does NOT run the FastAPI lifespan, so the seeds
    that normally run at startup are invoked explicitly here against the
    stubbed DB.
    """
    from app.db.seed import run_seeds
    from app.main import create_app

    app = create_app()
    await run_seeds()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Helpers ───────────────────────────────────────────────────────────────


def admin_token() -> str:
    """Mirror the frontend's dev-token format: `dev_<base64(json)>`."""
    import base64
    import json

    payload = json.dumps({"email": "admin@anveksha.dev", "role": "admin"})
    return "dev_" + base64.b64encode(payload.encode()).decode()


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token()}"}
