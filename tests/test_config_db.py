"""Database connection config — the pooled-vs-direct URL split.

`DATABASE_URL` (pooled, Supavisor transaction mode) drives all runtime
app traffic; `DATABASE_MIGRATION_URL` (direct) is used only by Alembic.
Both are plain optional strings (no component-part assembly, unlike the
old Mongo config) since Supabase hands out full connection strings
directly from its dashboard's Connect panel.
"""

from app.core.config import Settings


def test_test_database_url_has_a_local_default(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    s = Settings(_env_file=None)
    # Never the real Supabase project — always the local docker-compose
    # postgres-test service.
    assert "localhost" in s.TEST_DATABASE_URL
    assert s.TEST_DATABASE_URL.startswith("postgresql+psycopg://")
