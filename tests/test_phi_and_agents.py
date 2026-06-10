"""PHI gating + agent registry tests."""

import base64
import json

import pytest
from httpx import AsyncClient


def _hdr(sub: str, role: str) -> dict[str, str]:
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}


COMPANY = ("usr_co_001", "company")
CANDIDATE = ("usr_cand_001", "candidate")
VERIFIER = ("usr_ver_001", "interviewer")
ADMIN = ("usr_adm_001", "admin")


# ─── PHI: company unlock flow ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_masks_locked_candidates(client: AsyncClient):
    r = await client.post(
        "/api/ai-search", json={"query": "kafka"}, headers=_hdr(*COMPANY)
    )
    body = r.json()
    names = [c["name"] for c in body["candidates"]]
    assert "Aarav Rao" not in names
    assert all(n.startswith("Candidate ") for n in names)
    # Scores + skills stay visible while locked.
    assert all(c["verificationScore"] > 0 for c in body["candidates"])
    assert all(c["locked"] is True for c in body["candidates"])


@pytest.mark.asyncio
async def test_unlock_reveals_and_spends_credits(client: AsyncClient):
    before = (await client.get("/api/companies/me/credits", headers=_hdr(*COMPANY))).json()

    r = await client.post(
        "/api/companies/candidates/cand_001/unlock", headers=_hdr(*COMPANY)
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["balance"] == before["balance"] - 50

    # Search now reveals cand_001 only.
    r = await client.post("/api/ai-search", json={"query": "x"}, headers=_hdr(*COMPANY))
    by_id = {c["id"]: c for c in r.json()["candidates"]}
    assert by_id["cand_001"]["name"] == "Aarav Rao"
    assert by_id["cand_002"]["name"] == "Candidate B"

    # Second unlock is a no-op (no double charge).
    r = await client.post(
        "/api/companies/candidates/cand_001/unlock", headers=_hdr(*COMPANY)
    )
    assert r.json().get("alreadyUnlocked") is True


@pytest.mark.asyncio
async def test_pipeline_masks_locked(client: AsyncClient):
    r = await client.get("/api/companies/pipeline", headers=_hdr(*COMPANY))
    cards = [c for lane in r.json().values() for c in lane]
    assert all(c["name"].startswith("Candidate ") for c in cards)


# ─── PHI: candidate booking hides verifier identity ───────────────────────

@pytest.mark.asyncio
async def test_booking_slots_hide_verifier_names(client: AsyncClient):
    r = await client.get("/api/interviews/catalog", headers=_hdr(*CANDIDATE))
    slots = r.json()["slotsByDay"]["d5"]
    assert all(s["verifier"] == "Anveksha Verifier" for s in slots)
    # Quality signal (rating) is preserved.
    assert all(s["rating"] > 0 for s in slots)


# ─── Agent registry ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_registry_lists_six_agents(client: AsyncClient):
    r = await client.get("/api/admin/agents", headers=_hdr(*ADMIN))
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()}
    assert ids == {
        "interviewer_brief", "report_generator", "gap_analyzer",
        "gray_analyzer", "candidate_search", "candidate_chat",
    }


@pytest.mark.asyncio
async def test_registry_patch_and_reset(client: AsyncClient):
    r = await client.patch(
        "/api/admin/agents/candidate_chat",
        json={"systemMessage": "Custom SM.", "temperature": 0.9},
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 200
    assert r.json()["systemMessage"] == "Custom SM."
    assert r.json()["temperature"] == 0.9
    assert r.json()["updatedBy"] == "usr_adm_001"

    r = await client.post(
        "/api/admin/agents/candidate_chat/reset", headers=_hdr(*ADMIN)
    )
    assert r.json()["systemMessage"] == r.json()["defaultSystemMessage"]


@pytest.mark.asyncio
async def test_registry_rejects_bogus_model(client: AsyncClient):
    r = await client.patch(
        "/api/admin/agents/gray_analyzer",
        json={"modelId": "mdl_nope"},
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_registry_admin_only(client: AsyncClient):
    r = await client.get("/api/admin/agents", headers=_hdr(*CANDIDATE))
    assert r.status_code == 403


# ─── Agent feature endpoints (fallback path — no LLM creds in tests) ──────

@pytest.mark.asyncio
async def test_on_demand_brief(client: AsyncClient):
    r = await client.post(
        "/api/verifier/sessions/ses_u1/brief",
        json={"skill": "Payments System Design"},
        headers=_hdr(*VERIFIER),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["agentId"] == "interviewer_brief"
    assert body["source"] == "fallback"
    assert "Prioritized probes" in body["output"]
    assert "Idempotency keys at PSP boundary" in body["output"]


@pytest.mark.asyncio
async def test_brief_requires_interviewer(client: AsyncClient):
    r = await client.post(
        "/api/verifier/sessions/ses_u1/brief", headers=_hdr(*CANDIDATE)
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_report_generation(client: AsyncClient):
    r = await client.post(
        "/api/verifier/reports/rpt_001/generate", headers=_hdr(*VERIFIER)
    )
    assert r.status_code == 200
    assert "Draft report" in r.json()["output"]


@pytest.mark.asyncio
async def test_gray_analysis_any_authenticated(client: AsyncClient):
    r = await client.post(
        "/api/agents/gray-analysis",
        json={"candidateId": "usr_cand_001"},
        headers=_hdr(*CANDIDATE),
    )
    assert r.status_code == 200
    assert "Kafka Streams" in r.json()["output"]


@pytest.mark.asyncio
async def test_chat_uses_alias_for_locked_candidate(client: AsyncClient):
    r = await client.post(
        "/api/companies/chat",
        json={"candidateId": "cand_001", "prompt": "Tell me about their Kafka skills"},
        headers=_hdr(*COMPANY),
    )
    assert r.status_code == 200
    assert "Aarav" not in r.text
    assert "Candidate A" in r.text
