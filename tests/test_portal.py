import base64
import json

import pytest
from httpx import AsyncClient


def _hdr(sub: str, role: str) -> dict[str, str]:
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}


AARAV = ("usr_cand_001", "candidate")
MAYA = ("usr_ver_001", "interviewer")


@pytest.mark.asyncio
async def test_privacy_get_defaults(client: AsyncClient):
    r = await client.get("/api/privacy/settings", headers=_hdr(*AARAV))
    assert r.status_code == 200
    body = r.json()
    assert body["discoverability"] == "verified-only"
    assert body["shareScore"] is True
    assert body["shareGray"] is False
    assert len(body["sharedReports"]) == 2


@pytest.mark.asyncio
async def test_privacy_patch_persists_per_user(client: AsyncClient):
    r = await client.patch(
        "/api/privacy/settings", json={"shareGray": True, "anonymousMode": True},
        headers=_hdr(*AARAV),
    )
    assert r.json()["shareGray"] is True
    assert r.json()["anonymousMode"] is True

    # Maya's settings are untouched.
    r = await client.get("/api/privacy/settings", headers=_hdr(*MAYA))
    assert r.json()["shareGray"] is False


@pytest.mark.asyncio
async def test_privacy_revoke_shared_report(client: AsyncClient):
    r = await client.delete(
        "/api/privacy/shared-reports/sr_002", headers=_hdr(*AARAV)
    )
    assert r.json() == {"ok": True}
    r = await client.get("/api/privacy/settings", headers=_hdr(*AARAV))
    assert [s["id"] for s in r.json()["sharedReports"]] == ["sr_001"]


@pytest.mark.asyncio
async def test_dossier_me_and_share(client: AsyncClient):
    r = await client.get("/api/dossier/me", headers=_hdr(*AARAV))
    assert r.status_code == 200
    body = r.json()
    assert body["candidateName"] == "Aarav Rao"
    assert body["ledger"]["dossierId"] == "ANV-2481"
    assert len(body["sessions"]) == 4
    assert body["isShared"] is False

    r = await client.post(
        f"/api/dossier/{body['id']}/share", headers=_hdr(*AARAV)
    )
    assert r.json()["ok"] is True
    assert r.json()["shareUrl"].endswith(body["id"])

    r = await client.get("/api/dossier/me", headers=_hdr(*AARAV))
    assert r.json()["isShared"] is True


@pytest.mark.asyncio
async def test_booking_catalog_and_schedule(client: AsyncClient):
    r = await client.get("/api/interviews/catalog", headers=_hdr(*AARAV))
    assert r.status_code == 200
    cat = r.json()
    assert cat["catalogId"] == "KAF-204"
    assert len(cat["days"]) == 7
    assert len(cat["slotsByDay"]["d5"]) == 5

    r = await client.post(
        "/api/interviews/schedule",
        json={"dayId": "d5", "slotId": "s2"},
        headers=_hdr(*AARAV),
    )
    assert r.status_code == 200
    booked = r.json()
    assert booked["status"] == "scheduled"
    assert booked["dayId"] == "d5"
    assert booked["catalog"]["catalogId"] == "KAF-204"

    # New booking lands in my-interviews.
    r = await client.get("/api/interviews/my-interviews", headers=_hdr(*AARAV))
    assert any(i["id"] == booked["id"] for i in r.json())


@pytest.mark.asyncio
async def test_live_session_snapshot(client: AsyncClient):
    r = await client.get(
        "/api/interviews/session/KAF-88421", headers=_hdr(*AARAV)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "live"
    assert len(body["transcript"]) == 5
    assert body["phases"][2]["active"] is True
