import base64
import json

import pytest
from httpx import AsyncClient


def _hdr(sub: str, role: str) -> dict[str, str]:
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}


VERIFIER = ("usr_ver_001", "interviewer")
CANDIDATE = ("usr_cand_001", "candidate")


@pytest.mark.asyncio
async def test_candidate_forbidden(client: AsyncClient):
    r = await client.get("/api/verifier/queue", headers=_hdr(*CANDIDATE))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_queue_shape(client: AsyncClient):
    r = await client.get("/api/verifier/queue", headers=_hdr(*VERIFIER))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stats"]["sessionCount"] == 247
    assert len(body["live"]) == 1
    assert body["live"][0]["candidate"] == "Aarav Rao"
    assert len(body["upcoming"]) == 3


@pytest.mark.asyncio
async def test_next_brief(client: AsyncClient):
    r = await client.get("/api/verifier/next-brief", headers=_hdr(*VERIFIER))
    assert r.status_code == 200
    assert r.json()["candidate"] == "Priya Nair"
    assert len(r.json()["prioritizedProbes"]) == 3


@pytest.mark.asyncio
async def test_pending_reports_and_detail(client: AsyncClient):
    r = await client.get("/api/verifier/pending-reports", headers=_hdr(*VERIFIER))
    assert r.status_code == 200
    assert [p["id"] for p in r.json()] == ["rpt_001", "rpt_002"]

    r = await client.get("/api/verifier/reports/rpt_002", headers=_hdr(*VERIFIER))
    assert r.status_code == 200
    env = r.json()
    assert env["report"]["candidateName"] == "Omar Haddad"
    assert len(env["report"]["sections"]) == 6
    assert len(env["suggestedGaps"]) == 3


@pytest.mark.asyncio
async def test_unknown_report_falls_back(client: AsyncClient):
    r = await client.get("/api/verifier/reports/rpt_bogus", headers=_hdr(*VERIFIER))
    assert r.status_code == 200
    assert r.json()["report"]["id"] == "rpt_001"


@pytest.mark.asyncio
async def test_patch_report_persists_whitelisted_fields(client: AsyncClient):
    r = await client.patch(
        "/api/verifier/reports/rpt_001",
        json={"overallScore": 81, "evil": "ignored"},
        headers=_hdr(*VERIFIER),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["report"]["overallScore"] == 81
    # Echoes the raw patch (mock parity) but doesn't persist unknown keys.
    assert body["patched"]["evil"] == "ignored"
    assert "evil" not in body["report"]


@pytest.mark.asyncio
async def test_publish_removes_from_pending(client: AsyncClient):
    r = await client.post(
        "/api/verifier/reports/rpt_002/publish", headers=_hdr(*VERIFIER)
    )
    assert r.json() == {"ok": True, "status": "published"}
    r = await client.get("/api/verifier/pending-reports", headers=_hdr(*VERIFIER))
    assert all(p["id"] != "rpt_002" for p in r.json())


@pytest.mark.asyncio
async def test_governance(client: AsyncClient):
    r = await client.get("/api/verifier/governance", headers=_hdr(*VERIFIER))
    assert r.status_code == 200
    assert r.json()["reliability"] == 98
    assert len(r.json()["signals"]) == 4


@pytest.mark.asyncio
async def test_slot_lifecycle(client: AsyncClient):
    r = await client.get("/api/verifier/my-slots", headers=_hdr(*VERIFIER))
    assert len(r.json()) == 7

    r = await client.post(
        "/api/verifier/my-slots",
        json={"day": "Tue", "time": "16:00", "duration": 30, "skill": "Kafka"},
        headers=_hdr(*VERIFIER),
    )
    assert r.status_code == 200
    new_slot = r.json()
    assert new_slot["booked"] is False
    assert new_slot["day"] == "Tue"

    r = await client.delete(
        f"/api/verifier/my-slots/{new_slot['id']}", headers=_hdr(*VERIFIER)
    )
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_profile_roundtrip(client: AsyncClient):
    r = await client.get("/api/verifier/my-profile", headers=_hdr(*VERIFIER))
    assert r.json()["name"] == "Deepa Krishnan"

    r = await client.patch(
        "/api/verifier/my-profile",
        json={"bio": "Updated bio."},
        headers=_hdr(*VERIFIER),
    )
    assert r.status_code == 200
    assert r.json()["bio"] == "Updated bio."
    # Untouched fields preserved
    assert r.json()["rating"] == 4.9


@pytest.mark.asyncio
async def test_earnings(client: AsyncClient):
    r = await client.get("/api/verifier/earnings", headers=_hdr(*VERIFIER))
    assert r.status_code == 200
    assert r.json()["ytdAmount"] == 332700
    assert len(r.json()["months"]) == 4
    assert len(r.json()["rateCard"]) == 5
