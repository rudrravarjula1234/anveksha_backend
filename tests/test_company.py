import base64
import json

import pytest
from httpx import AsyncClient


def _hdr(sub: str, role: str) -> dict[str, str]:
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}


COMPANY = ("usr_co_001", "company")
ADMIN = ("usr_adm_001", "admin")


@pytest.mark.asyncio
async def test_company_me(client: AsyncClient):
    r = await client.get("/api/companies/me", headers=_hdr(*COMPANY))
    assert r.status_code == 200
    assert r.json()["primaryDomain"] == "northstack.co"


@pytest.mark.asyncio
async def test_interviewer_domain_guard(client: AsyncClient):
    r = await client.post(
        "/api/companies/me/interviewers",
        json={"displayName": "S. Bose", "title": "Senior Eng", "email": "sbose@gmail.com"},
        headers=_hdr(*COMPANY),
    )
    assert r.status_code == 400
    assert r.json()["code"] == "domain_mismatch"


@pytest.mark.asyncio
async def test_interviewer_lifecycle_and_credits(client: AsyncClient):
    # Add (valid domain) → verify → simulate session earns 200 credits
    r = await client.post(
        "/api/companies/me/interviewers",
        json={"displayName": "S. Bose", "title": "Senior Eng", "email": "sbose@northstack.co", "specialties": ["Kafka"]},
        headers=_hdr(*COMPANY),
    )
    assert r.status_code == 201
    new_id = r.json()["id"]
    assert r.json()["verified"] is False

    r = await client.post(
        f"/api/companies/me/interviewers/{new_id}/verify-email", headers=_hdr(*COMPANY)
    )
    assert r.json()["verified"] is True

    before = (await client.get("/api/companies/me/credits", headers=_hdr(*COMPANY))).json()
    r = await client.post(
        "/api/companies/me/credits/earn",
        json={"amount": 200, "reason": "External session · simulated", "interviewerId": new_id},
        headers=_hdr(*COMPANY),
    )
    after = r.json()
    assert after["balance"] == before["balance"] + 200

    # Interviewer external sessions bumped
    r = await client.get("/api/companies/me/interviewers", headers=_hdr(*COMPANY))
    fresh = next(i for i in r.json() if i["id"] == new_id)
    assert fresh["externalSessions"] == 1


@pytest.mark.asyncio
async def test_credits_seeded_balance_and_overspend(client: AsyncClient):
    r = await client.get("/api/companies/me/credits", headers=_hdr(*COMPANY))
    body = r.json()
    assert body["balance"] == 570  # 800 earned - 230 spent
    assert len(body["ledger"]) == 7

    r = await client.post(
        "/api/companies/me/credits/spend",
        json={"amount": 99999, "reason": "too much"},
        headers=_hdr(*COMPANY),
    )
    assert r.status_code == 402


@pytest.mark.asyncio
async def test_credit_rate_admin_only(client: AsyncClient):
    r = await client.get("/api/admin/credit-rate", headers=_hdr(*COMPANY))
    assert r.status_code == 403

    r = await client.get("/api/admin/credit-rate", headers=_hdr(*ADMIN))
    assert r.json()["rupeesPerCredit"] == 10

    r = await client.patch(
        "/api/admin/credit-rate", json={"rupeesPerCredit": 15}, headers=_hdr(*ADMIN)
    )
    assert r.json()["rupeesPerCredit"] == 15


@pytest.mark.asyncio
async def test_team_and_billing(client: AsyncClient):
    r = await client.get("/api/company/team", headers=_hdr(*COMPANY))
    assert len(r.json()) == 4

    r = await client.post(
        "/api/company/team",
        json={"email": "new.hire@northstack.co", "role": "Recruiter"},
        headers=_hdr(*COMPANY),
    )
    assert r.status_code == 201
    member_id = r.json()["id"]

    r = await client.delete(f"/api/company/team/{member_id}", headers=_hdr(*COMPANY))
    assert r.json() == {"ok": True}

    r = await client.get("/api/company/billing", headers=_hdr(*COMPANY))
    assert r.json()["summary"]["plan"] == "Enterprise"
    assert len(r.json()["invoices"]) == 4


@pytest.mark.asyncio
async def test_gray_followups(client: AsyncClient):
    r = await client.get("/api/company/gray-followups", headers=_hdr(*COMPANY))
    assert len(r.json()) == 4

    r = await client.post(
        "/api/company/gray-followups/fu_001/remind", headers=_hdr(*COMPANY)
    )
    assert r.json()["ok"] is True

    r = await client.delete("/api/company/gray-followups/fu_003", headers=_hdr(*COMPANY))
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_ai_search_with_min_score(client: AsyncClient):
    r = await client.post(
        "/api/ai-search",
        json={"query": "kafka people", "filters": {"minScore": 80}},
        headers=_hdr(*COMPANY),
    )
    assert r.status_code == 200
    scores = [c["verificationScore"] for c in r.json()["candidates"]]
    assert all(s >= 80 for s in scores)
    assert r.json()["query"] == "kafka people"


@pytest.mark.asyncio
async def test_pipeline_move_persists(client: AsyncClient):
    r = await client.get("/api/companies/pipeline", headers=_hdr(*COMPANY))
    board = r.json()
    assert len(board["investigating"]) == 2

    r = await client.post(
        "/api/companies/pipeline/cand_001/move",
        json={"stage": "shortlist"},
        headers=_hdr(*COMPANY),
    )
    assert r.json()["ok"] is True

    r = await client.get("/api/companies/pipeline", headers=_hdr(*COMPANY))
    board = r.json()
    assert any(c["candidateId"] == "cand_001" for c in board["shortlist"])
    assert all(c["candidateId"] != "cand_001" for c in board["investigating"])


@pytest.mark.asyncio
async def test_followup_request(client: AsyncClient):
    r = await client.get("/api/companies/followup/skills", headers=_hdr(*COMPANY))
    assert len(r.json()) == 4

    r = await client.post(
        "/api/companies/followup",
        json={"candidateId": "cand_001", "skills": ["Kafka Streams"], "message": "Please verify"},
        headers=_hdr(*COMPANY),
    )
    assert r.json()["ok"] is True
    assert r.json()["requestId"].startswith("fr_")


@pytest.mark.asyncio
async def test_chat_streams_text(client: AsyncClient):
    r = await client.post(
        "/api/companies/chat",
        json={"candidateId": "cand_001", "prompt": "Does Aarav know system design?"},
        headers=_hdr(*COMPANY),
    )
    assert r.status_code == 200
    assert "System Design (82/100)" in r.text
