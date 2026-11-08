
import pytest
from httpx import AsyncClient

from tests.helpers import hdr as _hdr

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
    assert booked["scheduled_date"].endswith(".000Z")

    # The new booking lands in my-interviews, next to the seeded ones...
    r = await client.get("/api/interviews/my-interviews", headers=_hdr(*AARAV))
    assert {"int_001", "int_002", "int_003", booked["id"]} <= {i["id"] for i in r.json()}

    # ...and nobody else's.
    r = await client.get("/api/interviews/my-interviews", headers=_hdr(*MAYA))
    theirs = {i["id"] for i in r.json()}
    assert booked["id"] not in theirs and "int_001" not in theirs


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


# A caller with no users row (possible with dev tokens) must never be
# served, or write into, the demo candidate's records.
GHOST = ("usr_not_seeded", "candidate")


@pytest.mark.asyncio
async def test_unseeded_caller_gets_nothing_of_the_demo_candidate(client: AsyncClient):
    r = await client.get("/api/privacy/settings", headers=_hdr(*GHOST))
    assert r.status_code == 404
    r = await client.patch("/api/privacy/settings", json={"shareGray": True}, headers=_hdr(*GHOST))
    assert r.status_code == 404
    r = await client.get("/api/dossier/me", headers=_hdr(*GHOST))
    assert r.status_code == 404
    r = await client.post("/api/interviews/schedule", json={"dayId": "d5", "slotId": "s2"}, headers=_hdr(*GHOST))
    assert r.status_code == 403
    r = await client.get("/api/interviews/my-interviews", headers=_hdr(*GHOST))
    assert r.json() == []

    # And Aarav's settings were not touched by the attempted patch.
    r = await client.get("/api/privacy/settings", headers=_hdr(*AARAV))
    assert r.json()["shareGray"] is False


@pytest.mark.asyncio
async def test_only_the_owner_can_share_a_dossier(client: AsyncClient):
    dossier_id = (await client.get("/api/dossier/me", headers=_hdr(*AARAV))).json()["id"]
    r = await client.post(f"/api/dossier/{dossier_id}/share", headers=_hdr(*MAYA))
    assert r.status_code == 404
    r = await client.post("/api/dossier/no-such-dossier/share", headers=_hdr(*AARAV))
    assert r.status_code == 404
    r = await client.get("/api/dossier/me", headers=_hdr(*AARAV))
    assert r.json()["isShared"] is False
