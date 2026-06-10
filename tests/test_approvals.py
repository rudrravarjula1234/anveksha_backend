import base64
import json

import pytest
from httpx import AsyncClient


def _hdr(sub: str, role: str) -> dict[str, str]:
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}


ADMIN = ("usr_adm_001", "admin")
AARAV = ("usr_cand_001", "candidate")


@pytest.mark.asyncio
async def test_overview_seeded(client: AsyncClient):
    r = await client.get("/api/admin/interviewer-approvals", headers=_hdr(*ADMIN))
    assert r.status_code == 200
    body = r.json()
    assert len(body["approvals"]) == 4
    assert len(body["invites"]) == 2
    assert len(body["active"]) == 2


@pytest.mark.asyncio
async def test_candidate_forbidden_on_admin_queue(client: AsyncClient):
    r = await client.get("/api/admin/interviewer-approvals", headers=_hdr(*AARAV))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_approve_grants_ledger_authority(client: AsyncClient):
    """Approving apr_001 (Aarav, .NET) must flip the approval, add him to
    the active list AND mark authority on his skill-ledger row."""
    r = await client.post(
        "/api/admin/interviewer-approvals/apr_001/approve",
        json={"note": "Strong record."},
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["reviewedBy"] == "usr_adm_001"
    assert body["decisionNote"] == "Strong record."

    # Active list gained Aarav
    r = await client.get("/api/admin/interviewer-approvals", headers=_hdr(*ADMIN))
    active_ids = [a["candidateId"] for a in r.json()["active"]]
    assert "usr_cand_001" in active_ids

    # Ledger reflects the authority + freelance promotion
    r = await client.get("/api/skills/ledger", headers=_hdr(*AARAV))
    ledger = r.json()
    assert ledger["interviewerStatus"]["mode"] == "freelance"
    net_row = next(s for s in ledger["skills"] if s["name"] == ".NET Microservices")
    assert net_row["authority"] is True


@pytest.mark.asyncio
async def test_reject_flow(client: AsyncClient):
    r = await client.post(
        "/api/admin/interviewer-approvals/apr_003/reject",
        json={"note": "Only one session."},
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_decide_unknown_id_404(client: AsyncClient):
    r = await client.post(
        "/api/admin/interviewer-approvals/apr_nope/approve", headers=_hdr(*ADMIN)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_self_request_creates_pending_row(client: AsyncClient):
    r = await client.post(
        "/api/candidate/interviewer-request",
        json={"skillName": "System Design", "skillScore": 82, "sessions": 1},
        headers=_hdr(*AARAV),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["origin"] == "self-requested"
    assert body["status"] == "pending"
    assert body["candidateName"] == "Aarav Rao"

    # Duplicate pending → 409
    r = await client.post(
        "/api/candidate/interviewer-request",
        json={"skillName": "System Design"},
        headers=_hdr(*AARAV),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_specialist_invite(client: AsyncClient):
    r = await client.post(
        "/api/admin/specialists/invite",
        json={
            "email": "guru@example.com",
            "firstName": "Guru",
            "lastName": "Raj",
            "skillName": "Kafka & Event Streams",
            "bio": "Wrote the book.",
            "externalProof": [{"id": "x1", "label": "Site", "url": "https://guru.dev"}],
        },
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 201
    assert r.json()["status"] == "sent"
    assert r.json()["invitedBy"] == "usr_adm_001"

    # Missing fields → 422
    r = await client.post(
        "/api/admin/specialists/invite",
        json={"email": "x@y.z"},
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 422
