"""Google OAuth sign-in flow.

The token verifier is monkeypatched — these tests cover the find-or-
create + role-resolution logic, not Google's signature validation
(which happens server-side at Google via the tokeninfo endpoint).
"""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings

CLIENT_ID = "712629791926-test.apps.googleusercontent.com"


@pytest.fixture
def google_configured(monkeypatch: pytest.MonkeyPatch):
    """Set GOOGLE_CLIENT_ID on the cached settings instance."""
    settings = get_settings()
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", CLIENT_ID)
    return settings


def _patch_claims(monkeypatch: pytest.MonkeyPatch, email: str, **extra):
    """Replace the verifier with one returning fixed claims."""
    from app.services import auth_service

    async def _fake_verify(id_token: str, audience: str):
        assert audience == CLIENT_ID
        return {
            "aud": audience,
            "email": email,
            "email_verified": "true",
            "given_name": extra.get("given_name", "Test"),
            "family_name": extra.get("family_name", "User"),
        }

    monkeypatch.setattr(auth_service, "verify_google_id_token", _fake_verify)


@pytest.mark.asyncio
async def test_seeded_admin_email_logs_in_as_admin(
    client: AsyncClient, google_configured, monkeypatch: pytest.MonkeyPatch
):
    _patch_claims(monkeypatch, "rudrravarjula1234@gmail.com")
    r = await client.post(
        "/api/auth/google-register",
        json={"google_token": "fake-id-token", "role": "candidate"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The seeded role wins over the request hint.
    assert body["user"]["email"] == "rudrravarjula1234@gmail.com"
    assert body["user"]["roles"] == ["admin"]
    assert body["user"]["id"] == "usr_adm_rajesh"
    assert body["access_token"].startswith("dev_")


@pytest.mark.asyncio
async def test_seeded_candidate_email_logs_in_as_candidate(
    client: AsyncClient, google_configured, monkeypatch: pytest.MonkeyPatch
):
    _patch_claims(monkeypatch, "rajesh.rudravarjula@gmail.com")
    r = await client.post(
        "/api/auth/google-register",
        json={"google_token": "fake-id-token"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["id"] == "usr_cand_rajesh"
    assert body["user"]["roles"] == ["candidate"]


@pytest.mark.asyncio
async def test_unknown_email_registers_new_candidate(
    client: AsyncClient, google_configured, monkeypatch: pytest.MonkeyPatch
):
    _patch_claims(monkeypatch, "newcomer@gmail.com", given_name="New", family_name="Comer")
    r = await client.post(
        "/api/auth/google-register",
        json={"google_token": "fake-id-token"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "newcomer@gmail.com"
    assert body["user"]["roles"] == ["candidate"]
    assert body["user"]["first_name"] == "New"
    assert body["user"]["id"].startswith("usr_g_")

    # Second login resolves the same user — no duplicate registration.
    r2 = await client.post(
        "/api/auth/google-register",
        json={"google_token": "fake-id-token"},
    )
    assert r2.json()["user"]["id"] == body["user"]["id"]


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(
    client: AsyncClient, google_configured, monkeypatch: pytest.MonkeyPatch
):
    from app.core.exceptions import UnauthorizedError
    from app.services import auth_service

    async def _reject(id_token: str, audience: str):
        raise UnauthorizedError("Invalid or expired Google token")

    monkeypatch.setattr(auth_service, "verify_google_id_token", _reject)
    r = await client.post(
        "/api/auth/google-register",
        json={"google_token": "garbage"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_without_client_id_falls_back_to_debug_stub(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    # Force the unconfigured state regardless of what .env / process env
    # carry — DEBUG stub then resolves by role, no token verification.
    monkeypatch.setattr(get_settings(), "GOOGLE_CLIENT_ID", None)
    r = await client.post(
        "/api/auth/google-register",
        json={"google_token": "anything", "role": "candidate"},
    )
    assert r.status_code == 200
    assert "candidate" in r.json()["user"]["roles"]
