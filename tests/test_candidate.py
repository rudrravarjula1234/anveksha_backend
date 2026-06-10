import base64
import json

import pytest
from httpx import AsyncClient


def _hdr(sub: str, role: str) -> dict[str, str]:
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}


AARAV = ("usr_cand_001", "candidate")
MAYA = ("usr_ver_001", "interviewer")
SURESH = ("usr_spec_001", "interviewer")


@pytest.mark.asyncio
async def test_skill_reports_list(client: AsyncClient):
    r = await client.get("/api/candidate/skill-reports", headers=_hdr(*AARAV))
    assert r.status_code == 200
    assert len(r.json()) == 5
    assert r.json()[0]["id"] == "SVR-KAF-88421"


@pytest.mark.asyncio
async def test_skill_report_detail_full_shape(client: AsyncClient):
    r = await client.get(
        "/api/candidate/skill-reports/SVR-KAF-88421", headers=_hdr(*AARAV)
    )
    assert r.status_code == 200
    d = r.json()
    assert d["score"] == 76
    assert len(d["rubric"]) == 6
    assert len(d["phases"]) == 5
    assert len(d["evidence"]) == 5
    assert d["gaps"][0]["area"] == "Producer epoch fencing"
    assert d["verifier"]["name"] == "Deepa Krishnan"


@pytest.mark.asyncio
async def test_skill_report_detail_404(client: AsyncClient):
    r = await client.get(
        "/api/candidate/skill-reports/SVR-NOPE", headers=_hdr(*AARAV)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_insights_act_lifecycle(client: AsyncClient):
    r = await client.get("/api/candidate/insights", headers=_hdr(*AARAV))
    assert len(r.json()) == 3
    assert all(i["acted"] is False for i in r.json())

    r = await client.post("/api/candidate/insights/in_001/act", headers=_hdr(*AARAV))
    assert r.json() == {"ok": True}

    r = await client.get("/api/candidate/insights", headers=_hdr(*AARAV))
    acted = next(i for i in r.json() if i["id"] == "in_001")
    assert acted["acted"] is True


@pytest.mark.asyncio
async def test_onboarding_ordered(client: AsyncClient):
    r = await client.get("/api/candidate/onboarding", headers=_hdr(*AARAV))
    ids = [s["id"] for s in r.json()]
    assert ids == ["s1", "s2", "s3", "s4"]


@pytest.mark.asyncio
async def test_public_profile_per_persona(client: AsyncClient):
    r = await client.get("/api/candidate/public-profile", headers=_hdr(*AARAV))
    assert r.json()["anvId"] == "ANV-2481"
    assert len(r.json()["timeline"]) == 6

    r = await client.get("/api/candidate/public-profile", headers=_hdr(*MAYA))
    assert r.json()["anvId"] == "ANV-7104"

    r = await client.get("/api/candidate/public-profile", headers=_hdr(*SURESH))
    body = r.json()
    assert body["anvId"] == "ANV-8801"
    assert body["constellation"] == []  # specialists have no ledger


@pytest.mark.asyncio
async def test_session_history(client: AsyncClient):
    r = await client.get("/api/candidate/session-history", headers=_hdr(*AARAV))
    rows = r.json()
    assert len(rows) == 6
    archived = next(x for x in rows if x["id"] == "SVR-DS-31001")
    assert archived["status"] == "archived"
    assert archived["note"] == "Retaken Feb 02"


@pytest.mark.asyncio
async def test_notifications_mark_read(client: AsyncClient):
    r = await client.get("/api/notifications", headers=_hdr(*AARAV))
    assert len(r.json()) == 5
    unread = [n for n in r.json() if not n["read"]]
    assert len(unread) == 3

    r = await client.post("/api/notifications/n_001/read", headers=_hdr(*AARAV))
    assert r.json() == {"ok": True, "id": "n_001"}

    r = await client.get("/api/notifications", headers=_hdr(*AARAV))
    n1 = next(n for n in r.json() if n["id"] == "n_001")
    assert n1["read"] is True


@pytest.mark.asyncio
async def test_profiles_me_derived_from_ledger(client: AsyncClient):
    r = await client.get("/api/profiles/me", headers=_hdr(*AARAV))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "usr_cand_001"
    assert ".NET Microservices" in body["skills"]
    assert body["average_score"] == 78

    r = await client.patch(
        "/api/profiles/me", json={"bio": "New bio"}, headers=_hdr(*AARAV)
    )
    assert r.json() == {"ok": True, "patched": {"bio": "New bio"}}
