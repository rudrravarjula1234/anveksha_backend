import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dev_login_candidate(client: AsyncClient):
    r = await client.post(
        "/api/auth/dev-login",
        json={"email": "candidate@anveksha.dev", "role": "candidate"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["id"] == "usr_cand_001"
    assert body["user"]["email"] == "aarav.rao@anveksha.dev"
    assert body["access_token"].startswith("dev_")
    assert body["refresh_token"].endswith(".refresh")
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_dev_login_explicit_user_id_specialist(client: AsyncClient):
    r = await client.post(
        "/api/auth/dev-login",
        json={"email": "interviewer@anveksha.dev", "role": "interviewer", "userId": "usr_spec_001"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["id"] == "usr_spec_001"
    assert r.json()["user"]["first_name"] == "Suresh"


@pytest.mark.asyncio
async def test_dev_login_interviewer_defaults_to_maya(client: AsyncClient):
    """Role-based lookup must skip the specialist persona."""
    r = await client.post(
        "/api/auth/dev-login",
        json={"email": "interviewer@anveksha.dev", "role": "interviewer"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["id"] == "usr_ver_001"


@pytest.mark.asyncio
async def test_me_roundtrip(client: AsyncClient):
    login = await client.post(
        "/api/auth/dev-login",
        json={"email": "admin@anveksha.dev", "role": "admin"},
    )
    token = login.json()["access_token"]
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["id"] == "usr_adm_001"
    assert r.json()["roles"] == ["admin"]


@pytest.mark.asyncio
async def test_refresh_reissues_for_same_user(client: AsyncClient):
    login = await client.post(
        "/api/auth/dev-login",
        json={"email": "candidate@anveksha.dev", "role": "candidate"},
    )
    refresh_token = login.json()["refresh_token"]
    r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == "usr_cand_001"
    assert r.json()["access_token"].startswith("dev_")


@pytest.mark.asyncio
async def test_refresh_rejects_garbage(client: AsyncClient):
    r = await client.post("/api/auth/refresh", json={"refresh_token": "nope"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_frontend_minted_token_accepted_on_admin_routes(pg_client: AsyncClient):
    """The frontend mock's makeDevToken({sub, role, iat}) shape must
    authenticate against real admin endpoints — this is the exact token
    in circulation when MSW passthrough flips an endpoint to us.

    Uses `pg_client` (not `client`) because /api/admin/models is now
    Postgres-backed — see the migration plan's Stage 2.
    """
    import base64
    import json

    token = "dev_" + base64.b64encode(
        json.dumps({"sub": "usr_adm_001", "role": "admin", "iat": 1700000000000}).encode()
    ).decode()
    r = await pg_client.get("/api/admin/models", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    r = await client.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
