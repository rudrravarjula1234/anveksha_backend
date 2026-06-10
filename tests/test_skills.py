import base64
import json

import pytest
from httpx import AsyncClient


def _token(sub: str, role: str) -> dict[str, str]:
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}


@pytest.mark.asyncio
async def test_ledger_requires_auth(client: AsyncClient):
    r = await client.get("/api/skills/ledger")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_candidate_gets_aarav_ledger(client: AsyncClient):
    r = await client.get("/api/skills/ledger", headers=_token("usr_cand_001", "candidate"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidateName"] == "Aarav Rao"
    assert body["dossierId"] == "ANV-2481"
    assert body["interviewerStatus"]["mode"] == "none"
    assert len(body["skills"]) == 6
    # Spot-check row shape
    net = next(s for s in body["skills"] if s["id"] == "skl_001")
    assert net["state"] == "verified"
    assert net["score"] == 87
    assert net["reportId"] == "SVR-NET-65433"


@pytest.mark.asyncio
async def test_freelancer_gets_maya_with_authorities(client: AsyncClient):
    r = await client.get("/api/skills/ledger", headers=_token("usr_ver_001", "interviewer"))
    assert r.status_code == 200
    body = r.json()
    assert body["candidateName"] == "Maya Iyer"
    assert body["interviewerStatus"]["mode"] == "freelance"
    assert len(body["interviewerStatus"]["authorities"]) == 2
    assert body["interviewerStatus"]["stats"]["monthlyEarnings"] == 84200
    authority_rows = [s for s in body["skills"] if s.get("authority")]
    assert len(authority_rows) == 2


@pytest.mark.asyncio
async def test_specialist_gets_suresh_empty_ledger(client: AsyncClient):
    r = await client.get("/api/skills/ledger", headers=_token("usr_spec_001", "interviewer"))
    assert r.status_code == 200
    body = r.json()
    assert body["interviewerStatus"]["mode"] == "specialist"
    assert body["skills"] == []
    assert body["interviewerStatus"]["bio"].startswith("Principal architect")
    assert len(body["interviewerStatus"]["externalProof"]) == 3
    # Specialist stats deliberately have no earnings.
    assert "monthlyEarnings" not in {
        k: v for k, v in body["interviewerStatus"]["stats"].items() if v is not None
    }


@pytest.mark.asyncio
async def test_unknown_user_falls_back_to_aarav(client: AsyncClient):
    r = await client.get("/api/skills/ledger", headers=_token("usr_nobody", "candidate"))
    assert r.status_code == 200
    assert r.json()["candidateName"] == "Aarav Rao"


@pytest.mark.asyncio
async def test_skills_list_returns_rows_only(client: AsyncClient):
    r = await client.get("/api/skills", headers=_token("usr_cand_001", "candidate"))
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) == 6
    assert rows[0]["name"] == ".NET Microservices"
