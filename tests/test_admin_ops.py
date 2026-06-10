import base64
import json

import pytest
from httpx import AsyncClient


def _hdr(sub: str, role: str) -> dict[str, str]:
    raw = json.dumps({"sub": sub, "role": role, "iat": 1700000000000})
    return {"Authorization": "Bearer dev_" + base64.b64encode(raw.encode()).decode()}


CANDIDATE = ("usr_cand_001", "candidate")


# ─── Auth gates ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient):
    r = await client.get("/api/admin/dashboard")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_candidate_forbidden(client: AsyncClient):
    r = await client.get("/api/admin/dashboard", headers=_hdr(*CANDIDATE))
    assert r.status_code == 403


# ─── Dashboard / overview / analytics ─────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/dashboard", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totalUsers"] == 3102
    assert body["activeVerifiers"] == 186
    assert body["reportsThisWeek"] == 312


@pytest.mark.asyncio
async def test_overview(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/overview", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["stats"]) == 6
    assert body["stats"][0] == {
        "label": "Sessions today",
        "value": 24,
        "sub": "↑ 8 vs yesterday",
        "color": "oxblood",
    }
    assert len(body["activity"]) == 6
    assert body["activity"][1]["tone"] == "verdant"


@pytest.mark.asyncio
async def test_analytics(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/analytics", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["topStats"]) == 4
    assert body["months"] == ["Nov", "Dec", "Jan", "Feb", "Mar", "Apr"]
    assert body["sessions"] == [180, 224, 312, 348, 401, 448]
    assert body["topSkills"][0] == {"name": "System Design", "share": 38}


# ─── Users ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_users_roles_update_persists(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/users", headers=admin_headers)
    assert r.status_code == 200
    assert [u["id"] for u in r.json()] == [
        "usr_cand_001",
        "usr_ver_001",
        "usr_co_001",
        "usr_co_002",
        "usr_adm_001",
    ]

    r = await client.put(
        "/api/admin/users/usr_cand_001/roles",
        json={"roles": ["candidate", "interviewer"]},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "userId": "usr_cand_001",
        "roles": ["candidate", "interviewer"],
    }

    r = await client.get("/api/admin/users", headers=admin_headers)
    user = next(u for u in r.json() if u["id"] == "usr_cand_001")
    assert user["roles"] == ["candidate", "interviewer"]


@pytest.mark.asyncio
async def test_deactivate_user_persists(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.post(
        "/api/admin/users/usr_cand_001/deactivate", headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "userId": "usr_cand_001"}

    r = await client.get("/api/admin/users", headers=admin_headers)
    user = next(u for u in r.json() if u["id"] == "usr_cand_001")
    assert user["is_active"] is False

    # Propagates to the auth users collection — the dev token now 403s.
    r = await client.get("/api/candidate/insights", headers=_hdr(*CANDIDATE))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_unknown_user_404(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.put(
        "/api/admin/users/usr_bogus/roles",
        json={"roles": ["candidate"]},
        headers=admin_headers,
    )
    assert r.status_code == 404


# ─── Bots (simple — /api/bots) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bots_simple_list_and_create(client: AsyncClient):
    # Any authenticated principal — the mock has no role gate.
    r = await client.get("/api/bots", headers=_hdr(*CANDIDATE))
    assert r.status_code == 200
    bots = r.json()
    assert len(bots) == 6
    assert bots[0]["id"] == "BOT-001"
    assert bots[0]["name"] == "Bob"

    r = await client.post(
        "/api/bots",
        json={"name": "Nina", "description": "Go systems bot."},
        headers=_hdr(*CANDIDATE),
    )
    assert r.status_code == 200
    bot = r.json()
    assert bot["id"].startswith("bot_")
    assert bot["status"] == "draft"
    assert bot["type"] == "interviewer"
    assert bot["model"] == "claude-opus-4-7"
    assert bot["sessionsRun"] == 0

    r = await client.get("/api/bots", headers=_hdr(*CANDIDATE))
    assert len(r.json()) == 7


@pytest.mark.asyncio
async def test_bots_simple_requires_auth(client: AsyncClient):
    r = await client.get("/api/bots")
    assert r.status_code == 401


# ─── Feature flags (simple list) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_feature_flag_toggle_persists(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/feature-flags", headers=admin_headers)
    assert r.status_code == 200
    flags = r.json()
    assert len(flags) == 9
    impersonate = next(f for f in flags if f["key"] == "admin.impersonate")
    assert impersonate["enabled"] is False

    r = await client.put(
        "/api/admin/feature-flags/admin.impersonate",
        json={"enabled": True},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["key"] == "admin.impersonate"

    r = await client.get("/api/admin/feature-flags", headers=admin_headers)
    impersonate = next(f for f in r.json() if f["key"] == "admin.impersonate")
    assert impersonate["enabled"] is True


@pytest.mark.asyncio
async def test_permissions(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/permissions", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert {"role": "admin", "permissions": ["*"]} in body
    assert len(body) == 5


# ─── Dossiers ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dossier_publish_flips_status(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/dossiers", headers=admin_headers)
    draft = next(d for d in r.json() if d["id"] == "SVR-PAY-91001")
    assert draft["status"] == "draft"

    r = await client.post(
        "/api/admin/dossiers/SVR-PAY-91001/publish", headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = await client.get("/api/admin/dossiers", headers=admin_headers)
    published = next(d for d in r.json() if d["id"] == "SVR-PAY-91001")
    assert published["status"] == "published"


@pytest.mark.asyncio
async def test_dossier_lifecycle(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.post(
        "/api/admin/dossiers",
        json={"candidate": "Li Wei", "skill": "Postgres Internals", "verifier": "R. Kapoor"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    dossier = r.json()
    assert dossier["id"].startswith("svr_")
    assert dossier["status"] == "draft"
    assert dossier["score"] == 0

    r = await client.patch(
        f"/api/admin/dossiers/{dossier['id']}",
        json={"score": 81, "status": "in-review"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["score"] == 81
    assert r.json()["status"] == "in-review"
    # Untouched fields preserved
    assert r.json()["candidate"] == "Li Wei"

    r = await client.delete(f"/api/admin/dossiers/{dossier['id']}", headers=admin_headers)
    assert r.json() == {"ok": True}

    r = await client.get("/api/admin/dossiers", headers=admin_headers)
    assert all(d["id"] != dossier["id"] for d in r.json())


# ─── Slots ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slot_create_and_block(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/slots", headers=admin_headers)
    assert len(r.json()) == 7

    r = await client.post(
        "/api/admin/slots",
        json={"verifier": "D. Krishnan", "day": "Sat Apr 26", "time": "10:00"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    slot = r.json()
    assert slot["id"].startswith("slt_")
    assert slot["booked"] is False
    assert slot["duration"] == 60
    assert slot["skill"] == "Any"

    r = await client.post("/api/admin/slots/slt_2/block", headers=admin_headers)
    assert r.json() == {"ok": True}

    r = await client.get("/api/admin/slots", headers=admin_headers)
    ids = [s["id"] for s in r.json()]
    assert "slt_2" not in ids
    assert slot["id"] in ids


# ─── Verifiers ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verifier_suspend_and_approve(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/verifiers", headers=admin_headers)
    assert len(r.json()) == 8

    r = await client.post("/api/admin/verifiers/v_001/suspend", headers=admin_headers)
    assert r.json() == {"ok": True}
    r = await client.get("/api/admin/verifiers", headers=admin_headers)
    v1 = next(v for v in r.json() if v["id"] == "v_001")
    assert v1["tier"] == "probation"

    r = await client.post("/api/admin/verifiers/v_a01/approve", headers=admin_headers)
    assert r.json() == {"ok": True}
    r = await client.get("/api/admin/verifiers", headers=admin_headers)
    applicant = next(v for v in r.json() if v["id"] == "v_a01")
    assert applicant["tier"] == "active"
    assert applicant["since"] == "Apr 2026"


@pytest.mark.asyncio
async def test_verifier_invite_echo(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.post(
        "/api/admin/verifiers/invite",
        json={"email": "new@anveksha.dev", "specialization": "Rust · Systems"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "email": "new@anveksha.dev",
        "specialization": "Rust · Systems",
    }


# ─── Candidates / companies ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_candidates_list(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/candidates", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 6
    assert body[-1]["status"] == "blacklisted"


@pytest.mark.asyncio
async def test_company_impersonate(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/companies", headers=admin_headers)
    assert len(r.json()) == 5

    r = await client.post("/api/admin/companies/co_001/impersonate", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["companyId"] == "co_001"
    assert body["sessionId"].startswith("imp_")

    r = await client.post("/api/admin/companies/co_bogus/impersonate", headers=admin_headers)
    assert r.status_code == 404


# ─── Integrity ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_integrity_resolve(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/integrity", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["flags"]) == 5
    assert len(body["signals"]) == 6
    flag1 = next(f for f in body["flags"] if f["id"] == "flag_1")
    assert flag1["severity"] == "high"

    r = await client.post(
        "/api/admin/integrity/flag_1/resolve",
        json={"action": "Dossier suspended"},
        headers=admin_headers,
    )
    assert r.json() == {"ok": True}

    # Empty body falls back to the mock's default action.
    r = await client.post(
        "/api/admin/integrity/flag_2/resolve", json={}, headers=admin_headers
    )
    assert r.json() == {"ok": True}

    r = await client.get("/api/admin/integrity", headers=admin_headers)
    flags = {f["id"]: f for f in r.json()["flags"]}
    assert flags["flag_1"]["severity"] == "confirmed"
    assert flags["flag_1"]["action"] == "Dossier suspended"
    assert flags["flag_2"]["severity"] == "confirmed"
    assert flags["flag_2"]["action"] == "Resolved"


# ─── Feature flags (rich registry + state) ────────────────────────────────


@pytest.mark.asyncio
async def test_flags_toggle_and_reset(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/flags", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["registry"]) == 7
    assert body["state"]["admin.impersonate"] is False
    assert body["state"]["candidate.public_profile"] is True

    r = await client.put(
        "/api/admin/flags",
        json={"admin.impersonate": True, "candidate.insights": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["state"]["admin.impersonate"] is True
    assert r.json()["state"]["candidate.insights"] is False

    # Persisted across reads
    r = await client.get("/api/admin/flags", headers=admin_headers)
    assert r.json()["state"]["admin.impersonate"] is True

    r = await client.post("/api/admin/flags/reset", headers=admin_headers)
    assert r.json()["state"]["admin.impersonate"] is False
    assert r.json()["state"]["candidate.insights"] is True


@pytest.mark.asyncio
async def test_flags_group_toggle(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.post(
        "/api/admin/flags/group/Pilot%20Programs",
        json={"value": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    state = r.json()["state"]
    assert state["pilot.programs"] is False
    assert state["pilot.bulk_import"] is False
    assert state["pilot.analytics"] is False
    # Other groups untouched
    assert state["candidate.public_profile"] is True


# ─── RBAC ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rbac_perm_flip_persists(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.get("/api/admin/rbac", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert [role["id"] for role in body["roles"]] == ["candidate", "verifier", "company", "admin"]
    assert len(body["customRoles"]) == 3
    assert len(body["audit"]) == 6

    company = next(role for role in body["roles"] if role["id"] == "company")
    transcript = next(p for p in company["perms"] if p["id"] == "view_transcript")
    assert transcript["on"] is False

    r = await client.put(
        "/api/admin/rbac/company/view_transcript",
        json={"on": True},
        headers=admin_headers,
    )
    assert r.json() == {"ok": True}

    r = await client.get("/api/admin/rbac", headers=admin_headers)
    company = next(role for role in r.json()["roles"] if role["id"] == "company")
    transcript = next(p for p in company["perms"] if p["id"] == "view_transcript")
    assert transcript["on"] is True


@pytest.mark.asyncio
async def test_rbac_locked_perm_never_flips(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.put(
        "/api/admin/rbac/candidate/admin_access",
        json={"on": True},
        headers=admin_headers,
    )
    assert r.json() == {"ok": True}  # mock parity: ack but no-op

    r = await client.get("/api/admin/rbac", headers=admin_headers)
    candidate = next(role for role in r.json()["roles"] if role["id"] == "candidate")
    admin_access = next(p for p in candidate["perms"] if p["id"] == "admin_access")
    assert admin_access["on"] is False


@pytest.mark.asyncio
async def test_custom_role_lifecycle(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.post(
        "/api/admin/rbac/custom",
        json={
            "name": "QA Auditor",
            "baseRole": "admin",
            "desc": "Read-only audit access.",
            "overrides": {"manage_bots": False},
        },
        headers=admin_headers,
    )
    assert r.status_code == 200
    role = r.json()
    assert role["id"].startswith("cr_")
    assert role["members"] == 0
    assert role["overrides"] == {"manage_bots": False}

    r = await client.get("/api/admin/rbac", headers=admin_headers)
    assert len(r.json()["customRoles"]) == 4

    r = await client.delete(f"/api/admin/rbac/custom/{role['id']}", headers=admin_headers)
    assert r.json() == {"ok": True}

    r = await client.get("/api/admin/rbac", headers=admin_headers)
    assert len(r.json()["customRoles"]) == 3


# ─── Pilots + students ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pilots_simple_projects_full_shape(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.get("/api/admin/pilots", headers=admin_headers)
    assert r.status_code == 200
    pilots = r.json()
    assert [p["id"] for p in pilots] == ["PLT-001", "PLT-002", "PLT-003"]
    assert "dept" not in pilots[0]
    assert "assessments" not in pilots[0]

    r = await client.get("/api/admin/pilots-full", headers=admin_headers)
    full = r.json()
    assert full[0]["dept"] == "Computer Science"
    assert full[0]["assessments"] == ["ASS-001", "ASS-002", "ASS-004"]


@pytest.mark.asyncio
async def test_create_pilot(client: AsyncClient, admin_headers: dict[str, str]):
    r = await client.post(
        "/api/admin/pilots-full",
        json={"name": "VIT — Data Track", "college": "VIT Vellore"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    pilot = r.json()
    assert pilot["id"].startswith("plt_")
    assert pilot["status"] == "draft"
    assert pilot["students"] == 0
    assert pilot["dept"] == "Computer Science"
    assert pilot["batch"] == "2024-25"

    r = await client.get("/api/admin/pilots-full", headers=admin_headers)
    assert len(r.json()) == 4


@pytest.mark.asyncio
async def test_pilot_student_create_bumps_program_count(
    client: AsyncClient, admin_headers: dict[str, str]
):
    r = await client.get("/api/admin/pilot-students", headers=admin_headers)
    assert len(r.json()) == 6

    r = await client.post(
        "/api/admin/pilot-students",
        json={"name": "Divya Krish", "email": "divya@iitb.ac.in", "program": "PLT-001"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    student = r.json()
    assert student["id"].startswith("stu_")
    assert student["status"] == "registered"
    assert student["pending"] == 3
    assert student["avgScore"] == 0

    r = await client.get("/api/admin/pilots", headers=admin_headers)
    plt1 = next(p for p in r.json() if p["id"] == "PLT-001")
    assert plt1["students"] == 85  # 84 + 1


@pytest.mark.asyncio
async def test_pilot_student_import(client: AsyncClient, admin_headers: dict[str, str]):
    rows = [
        {"name": "A One", "email": "a1@bits.ac.in", "program": "PLT-002"},
        {"name": "B Two", "email": "b2@bits.ac.in", "program": "PLT-002"},
        {"name": "C Three", "email": "c3@nitt.edu", "program": "PLT-003"},
    ]
    r = await client.post(
        "/api/admin/pilot-students/import", json={"rows": rows}, headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "count": 3}

    r = await client.get("/api/admin/pilot-students", headers=admin_headers)
    assert len(r.json()) == 9

    r = await client.get("/api/admin/pilots", headers=admin_headers)
    by_id = {p["id"]: p for p in r.json()}
    assert by_id["PLT-002"]["students"] == 54  # 52 + 2
    assert by_id["PLT-003"]["students"] == 39  # 38 + 1
