
import pytest
from httpx import AsyncClient

from tests.helpers import hdr as _hdr

ADMIN = ("usr_adm_001", "admin")
CANDIDATE = ("usr_cand_001", "candidate")


@pytest.mark.asyncio
async def test_admin_full_list_seeded(client: AsyncClient):
    r = await client.get("/api/admin/assessments-full", headers=_hdr(*ADMIN))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 8
    kafka = next(a for a in items if a["id"] == "ASS-001")
    assert kafka["probes"] == [
        "Partitioning & ordering",
        "Consumer group semantics",
        "Exactly-once delivery",
        "Operational incidents",
    ]


@pytest.mark.asyncio
async def test_admin_slim_projection(client: AsyncClient):
    r = await client.get("/api/admin/assessments", headers=_hdr(*ADMIN))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 8
    # Slim shape must not leak the full fields
    assert "probes" not in items[0]
    assert "botIds" not in items[0]
    assert {"id", "slug", "title", "domain", "depth", "type", "duration", "price", "published", "sessions"} <= set(items[0].keys())


@pytest.mark.asyncio
async def test_catalog_only_published(client: AsyncClient):
    r = await client.get("/api/catalog", headers=_hdr(*CANDIDATE))
    assert r.status_code == 200
    items = r.json()
    # ASS-008 is unpublished — 7 of 8 ship.
    assert len(items) == 7
    assert all(a["id"] != "ASS-008" for a in items)
    # Catalog rows don't expose `published` or `probes`.
    assert "published" not in items[0]


@pytest.mark.asyncio
async def test_catalog_full_only_published(client: AsyncClient):
    r = await client.get("/api/catalog/full", headers=_hdr(*CANDIDATE))
    assert r.status_code == 200
    assert len(r.json()) == 7


@pytest.mark.asyncio
async def test_catalog_coupons_active_only(client: AsyncClient):
    r = await client.get("/api/catalog/coupons", headers=_hdr(*CANDIDATE))
    assert r.status_code == 200
    codes = [c["code"] for c in r.json()]
    assert "LAUNCH50" in codes
    assert "STRIPE200" not in codes  # inactive seed
    assert all("active" not in c for c in r.json())


@pytest.mark.asyncio
async def test_create_toggle_delete_lifecycle(client: AsyncClient):
    # Create — starts unpublished
    r = await client.post(
        "/api/admin/assessments-full",
        json={"title": "Go Backend", "domain": "Backend", "type": "bot"},
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["published"] is False
    assert created["sessions"] == 0
    new_id = created["id"]

    # Not in candidate catalog while unpublished
    r = await client.get("/api/catalog", headers=_hdr(*CANDIDATE))
    assert all(a["id"] != new_id for a in r.json())

    # Toggle publish → appears in catalog
    r = await client.post(
        f"/api/admin/assessments-full/{new_id}/toggle-publish", headers=_hdr(*ADMIN)
    )
    assert r.json() == {"ok": True}
    r = await client.get("/api/catalog", headers=_hdr(*CANDIDATE))
    assert any(a["id"] == new_id for a in r.json())

    # PATCH
    r = await client.patch(
        f"/api/admin/assessments-full/{new_id}",
        json={"price": 499},
        headers=_hdr(*ADMIN),
    )
    assert r.json()["price"] == 499

    # Delete
    r = await client.delete(f"/api/admin/assessments-full/{new_id}", headers=_hdr(*ADMIN))
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_admin_coupon_lifecycle(client: AsyncClient):
    # Create
    r = await client.post(
        "/api/admin/coupons",
        json={"code": "diwali25", "type": "percent", "value": 25, "desc": "Festive"},
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "DIWALI25"  # normalised to upper
    assert r.json()["active"] is True

    # Duplicate → 409
    r = await client.post(
        "/api/admin/coupons",
        json={"code": "DIWALI25", "type": "percent", "value": 25},
        headers=_hdr(*ADMIN),
    )
    assert r.status_code == 409

    # Toggle off → drops from candidate-facing list
    await client.post("/api/admin/coupons/DIWALI25/toggle", headers=_hdr(*ADMIN))
    r = await client.get("/api/catalog/coupons", headers=_hdr(*CANDIDATE))
    assert all(c["code"] != "DIWALI25" for c in r.json())

    # Delete
    r = await client.delete("/api/admin/coupons/DIWALI25", headers=_hdr(*ADMIN))
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_candidate_cannot_touch_admin_assessments(client: AsyncClient):
    r = await client.get("/api/admin/assessments-full", headers=_hdr(*CANDIDATE))
    assert r.status_code == 403
