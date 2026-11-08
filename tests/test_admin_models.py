"""Admin AI-model config endpoints — ported to Postgres (Stage 2 template
entity). Runs against the real local Postgres via the `pg_client` fixture
(transactional, rolled back per test).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_requires_admin_role(pg_client: AsyncClient):
    """No bearer → 401."""
    r = await pg_client.get("/api/admin/models")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_forbidden(pg_client: AsyncClient):
    """A candidate dev-token must not see admin endpoints."""
    import base64
    import json

    token = "dev_" + base64.b64encode(
        json.dumps({"email": "c@x.dev", "role": "candidate"}).encode()
    ).decode()
    r = await pg_client.get(
        "/api/admin/models", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_empty_list(pg_client: AsyncClient, admin_headers: dict[str, str]):
    r = await pg_client.get("/api/admin/models", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_then_list_then_patch_then_toggle_then_delete(
    pg_client: AsyncClient, admin_headers: dict[str, str]
):
    # Create
    create_body = {
        "name": "Claude Sonnet 4.5",
        "provider": "Anthropic",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-5",
        "contextWindow": 200_000,
        "costPer1kIn": 3.0,
        "costPer1kOut": 15.0,
        "notes": "Primary reasoning model",
    }
    r = await pg_client.post("/api/admin/models", json=create_body, headers=admin_headers)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["id"].startswith("mdl_")
    assert created["name"] == "Claude Sonnet 4.5"
    assert created["status"] == "active"
    new_id = created["id"]

    # List
    r = await pg_client.get("/api/admin/models", headers=admin_headers)
    assert r.status_code == 200
    assert any(m["id"] == new_id for m in r.json())

    # Patch (rename + bump context window)
    r = await pg_client.patch(
        f"/api/admin/models/{new_id}",
        json={"name": "Claude Sonnet 4.5 Updated", "contextWindow": 250_000},
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Claude Sonnet 4.5 Updated"
    assert body["contextWindow"] == 250_000

    # Toggle off
    r = await pg_client.post(f"/api/admin/models/{new_id}/toggle", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "inactive"

    # Toggle back on
    r = await pg_client.post(f"/api/admin/models/{new_id}/toggle", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    # Delete → 204, then 404 on subsequent fetch
    r = await pg_client.delete(f"/api/admin/models/{new_id}", headers=admin_headers)
    assert r.status_code == 204
    r = await pg_client.patch(
        f"/api/admin/models/{new_id}", json={"name": "x"}, headers=admin_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_rejects_unknown_provider(
    pg_client: AsyncClient, admin_headers: dict[str, str]
):
    r = await pg_client.post(
        "/api/admin/models",
        json={"name": "x", "provider": "FantasyAI", "model": "foo"},
        headers=admin_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_unknown_id_returns_404(
    pg_client: AsyncClient, admin_headers: dict[str, str]
):
    r = await pg_client.patch(
        "/api/admin/models/mdl_doesnotexist",
        json={"name": "x"},
        headers=admin_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_fallback_id_enforced_as_real_fk(
    pg_client: AsyncClient, admin_headers: dict[str, str]
):
    """New in the Postgres port: fallbackId is a real FK now (unenforced
    in the old Mongo repo). Pointing it at a nonexistent model must fail
    rather than silently storing a dangling reference."""
    r = await pg_client.post(
        "/api/admin/models",
        json={"name": "x", "provider": "OpenAI", "model": "gpt", "fallbackId": "mdl_doesnotexist"},
        headers=admin_headers,
    )
    assert r.status_code in (400, 409, 422)
