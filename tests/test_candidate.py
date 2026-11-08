
import pytest
from httpx import AsyncClient

from tests.helpers import hdr as _hdr

AARAV = ("usr_cand_001", "candidate")
MAYA = ("usr_ver_001", "interviewer")
SURESH = ("usr_spec_001", "interviewer")


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient):
    r = await client.get("/api/candidate/skill-reports")
    assert r.status_code == 401


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
async def test_per_user_scoping_blocks_cross_user_access(client: AsyncClient):
    """Regression test for the migration's per-user scoping fix: these
    endpoints used to return every row in the table to every caller
    (leftover single-demo-user behavior). Maya must not see Aarav's
    skill reports, insights, session history, notifications, or report
    detail — only her own (empty, since no data is seeded for her)."""
    for path in (
        "/api/candidate/skill-reports",
        "/api/candidate/insights",
        "/api/candidate/session-history",
        "/api/notifications",
    ):
        r = await client.get(path, headers=_hdr(*MAYA))
        assert r.status_code == 200, path
        assert r.json() == [], f"{path} leaked another user's rows to Maya"

    # Aarav's own report detail, fetched as Maya, must 404 — not just be
    # absent from a list, but actually inaccessible by direct id too.
    r = await client.get("/api/candidate/skill-reports/SVR-KAF-88421", headers=_hdr(*MAYA))
    assert r.status_code == 404

    # Sanity check the other direction: Aarav still sees his own data
    # (the fix filters by owner, it doesn't just block everyone).
    r = await client.get("/api/candidate/skill-reports", headers=_hdr(*AARAV))
    assert len(r.json()) == 5


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

    # The edit must round-trip: a subsequent GET reflects the saved bio.
    r = await client.get("/api/profiles/me", headers=_hdr(*AARAV))
    assert r.json()["bio"] == "New bio"


@pytest.mark.asyncio
async def test_profiles_me_patch_persists_all_fields(client: AsyncClient):
    patch = {
        "bio": "Distributed systems, sagas, and coffee.",
        "location": "Pune",
        "current_role": "Staff Backend Engineer",
        "experience_years": 8,
        "skills": ["Kubernetes", "Event Sourcing"],
    }
    r = await client.patch("/api/profiles/me", json=patch, headers=_hdr(*AARAV))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "patched": patch}

    r = await client.get("/api/profiles/me", headers=_hdr(*AARAV))
    assert r.status_code == 200
    body = r.json()
    assert body["bio"] == patch["bio"]
    assert body["location"] == patch["location"]
    assert body["current_role"] == patch["current_role"]
    assert body["experience_years"] == patch["experience_years"]
    assert body["skills"] == patch["skills"]

    # The profile-skills override must NOT clobber the verified ledger
    # rows that /api/skills and scoring are derived from.
    r = await client.get("/api/skills", headers=_hdr(*AARAV))
    assert r.status_code == 200
    names = [s["name"] for s in r.json()]
    assert ".NET Microservices" in names
