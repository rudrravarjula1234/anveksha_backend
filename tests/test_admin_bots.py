import pytest
from httpx import AsyncClient


async def _create_model(client: AsyncClient, admin_headers: dict[str, str]) -> str:
    r = await client.post(
        "/api/admin/models",
        json={
            "name": "GPT-4o",
            "provider": "OpenAI",
            "model": "gpt-4o",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.asyncio
async def test_requires_admin(client: AsyncClient):
    r = await client.get("/api/admin/bots")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_empty_list(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/bots", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_requires_existing_primary_model(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.post(
        "/api/admin/bots",
        json={
            "name": "Ghost",
            "primaryModelId": "mdl_doesnotexist",
            "specializations": ["Microservices"],
        },
        headers=admin_headers,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert "primaryModelId" in body["detail"]


@pytest.mark.asyncio
async def test_full_lifecycle(client: AsyncClient, admin_headers: dict[str, str]):
    model_id = await _create_model(client, admin_headers)

    # Create
    create_body = {
        "name": "Bob",
        "fullName": "Bob — Microservices Architect",
        "specializations": ["Microservices", ".NET"],
        "primaryModelId": model_id,
        "persona": "Direct, probing style.",
        "systemPrompt": "You are Bob…",
    }
    r = await client.post("/api/admin/bots", json=create_body, headers=admin_headers)
    assert r.status_code == 201, r.text
    bot = r.json()
    assert bot["id"].startswith("bot_")
    assert bot["name"] == "Bob"
    # Defaulted by service
    assert bot["status"] == "draft"
    assert bot["avatar"] == "B"
    assert bot["color"].startswith("#")
    bot_id = bot["id"]

    # List
    r = await client.get("/api/admin/bots", headers=admin_headers)
    assert r.status_code == 200
    assert any(b["id"] == bot_id for b in r.json())

    # Patch — rename + change specializations
    r = await client.patch(
        f"/api/admin/bots/{bot_id}",
        json={"specializations": ["CQRS", "Resilience"]},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["specializations"] == ["CQRS", "Resilience"]

    # Toggle draft → active
    r = await client.post(f"/api/admin/bots/{bot_id}/toggle", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    # Toggle active → inactive
    r = await client.post(f"/api/admin/bots/{bot_id}/toggle", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "inactive"

    # Delete
    r = await client.delete(f"/api/admin/bots/{bot_id}", headers=admin_headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_patch_rejects_invalid_model_reference(
    client: AsyncClient, admin_headers: dict[str, str]
):
    model_id = await _create_model(client, admin_headers)
    r = await client.post(
        "/api/admin/bots",
        json={"name": "Test", "primaryModelId": model_id},
        headers=admin_headers,
    )
    bot_id = r.json()["id"]
    r = await client.patch(
        f"/api/admin/bots/{bot_id}",
        json={"primaryModelId": "mdl_bogus"},
        headers=admin_headers,
    )
    assert r.status_code == 422
