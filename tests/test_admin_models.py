import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_requires_admin_role(client: AsyncClient):
    """No bearer → 401."""
    r = await client.get("/api/admin/models")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_forbidden(client: AsyncClient):
    """A candidate dev-token must not see admin endpoints."""
    import base64
    import json

    token = "dev_" + base64.b64encode(
        json.dumps({"email": "c@x.dev", "role": "candidate"}).encode()
    ).decode()
    r = await client.get(
        "/api/admin/models", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_empty_list(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/models", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_then_list_then_patch_then_toggle_then_delete(
    client: AsyncClient, admin_headers: dict[str, str]
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
    r = await client.post("/api/admin/models", json=create_body, headers=admin_headers)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["id"].startswith("mdl_")
    assert created["name"] == "Claude Sonnet 4.5"
    assert created["status"] == "active"
    new_id = created["id"]

    # List
    r = await client.get("/api/admin/models", headers=admin_headers)
    assert r.status_code == 200
    assert any(m["id"] == new_id for m in r.json())

    # Patch (rename + bump context window)
    r = await client.patch(
        f"/api/admin/models/{new_id}",
        json={"name": "Claude Sonnet 4.5 Updated", "contextWindow": 250_000},
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Claude Sonnet 4.5 Updated"
    assert body["contextWindow"] == 250_000

    # Toggle off
    r = await client.post(f"/api/admin/models/{new_id}/toggle", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "inactive"

    # Toggle back on
    r = await client.post(f"/api/admin/models/{new_id}/toggle", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    # Delete → 204, then 404 on subsequent fetch
    r = await client.delete(f"/api/admin/models/{new_id}", headers=admin_headers)
    assert r.status_code == 204
    r = await client.patch(
        f"/api/admin/models/{new_id}", json={"name": "x"}, headers=admin_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_rejects_unknown_provider(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.post(
        "/api/admin/models",
        json={"name": "x", "provider": "FantasyAI", "model": "foo"},
        headers=admin_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_unknown_id_returns_404(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.patch(
        "/api/admin/models/mdl_doesnotexist",
        json={"name": "x"},
        headers=admin_headers,
    )
    assert r.status_code == 404
