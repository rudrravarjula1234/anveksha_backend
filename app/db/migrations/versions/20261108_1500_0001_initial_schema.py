"""initial schema

Squashed on 2026-11-08 from the 28 migrations written during the move from
MongoDB to Postgres (c4094076e914 ... c3d4e5f6a7b8). It builds the schema
those migrations produced, in one step:

1. `anveksha_app`, the least-privilege runtime role (created if missing).
2. Every table, index and constraint.
3. `set_updated_at()`, and a BEFORE UPDATE trigger on every table with an
   `updated_at` column.
4. Statement-level triggers that keep `token_usage_model_totals` and
   `workflow_run_status_counts` in step with `token_usage` and
   `workflow_runs` on insert, update, delete and truncate. The subtract
   half locks rollup rows in key order first, so concurrent bulk writes
   can't deadlock.
5. Grants for `anveksha_app`, including default privileges for tables
   created later.
6. Row-level security on every table in `public`, with one permissive
   policy for `anveksha_app`. Supabase exposes `public` to the anon key,
   so a table without RLS is world-readable. A later migration that adds a
   table calls `app.db.rls.enable_rls_sql`.

Revision ID: 0001
Revises:
Create Date: 2026-11-08 15:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _function(name: str, body: str, returns: str = "NULL") -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {name}() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
            {body}
            RETURN {returns};
        END;
        $$;
    """


# ── token_usage → token_usage_model_totals ──────────────────────────────

_TOKENS_ADD = """
    INSERT INTO token_usage_model_totals AS t
        (model_name, requests, input_tokens, output_tokens, total_tokens, total_cost)
    SELECT model_name, count(*), sum(input_tokens), sum(output_tokens), sum(total_tokens), sum(total_cost)
    FROM new_rows GROUP BY model_name ORDER BY model_name
    ON CONFLICT (model_name) DO UPDATE SET
        requests = t.requests + EXCLUDED.requests,
        input_tokens = t.input_tokens + EXCLUDED.input_tokens,
        output_tokens = t.output_tokens + EXCLUDED.output_tokens,
        total_tokens = t.total_tokens + EXCLUDED.total_tokens,
        total_cost = t.total_cost + EXCLUDED.total_cost;
"""

_TOKENS_SUBTRACT = """
    UPDATE token_usage_model_totals t SET
        requests = t.requests - o.requests,
        input_tokens = t.input_tokens - o.input_tokens,
        output_tokens = t.output_tokens - o.output_tokens,
        total_tokens = t.total_tokens - o.total_tokens,
        total_cost = t.total_cost - o.total_cost
    FROM (
        SELECT model_name, count(*) AS requests, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens,
               sum(total_tokens) AS total_tokens, sum(total_cost) AS total_cost
        FROM old_rows GROUP BY model_name ORDER BY model_name
    ) o
    WHERE t.model_name = o.model_name;
    DELETE FROM token_usage_model_totals WHERE requests <= 0;
"""


def _lock_tokens(keys: str) -> str:
    return f"""
    PERFORM 1 FROM token_usage_model_totals
    WHERE model_name IN ({keys}) ORDER BY model_name FOR UPDATE;
"""


_TOKENS_OLD_KEYS = "SELECT model_name FROM old_rows"
_TOKENS_ALL_KEYS = "SELECT model_name FROM old_rows UNION SELECT model_name FROM new_rows"


# ── workflow_runs → workflow_run_status_counts ──────────────────────────

_RUNS_ADD = """
    INSERT INTO workflow_run_status_counts AS t (status, runs)
    SELECT status, count(*) FROM new_rows GROUP BY status ORDER BY status
    ON CONFLICT (status) DO UPDATE SET runs = t.runs + EXCLUDED.runs;
"""

_RUNS_SUBTRACT = """
    UPDATE workflow_run_status_counts t SET runs = t.runs - o.runs
    FROM (SELECT status, count(*) AS runs FROM old_rows GROUP BY status) o
    WHERE t.status = o.status;
    DELETE FROM workflow_run_status_counts WHERE runs <= 0;
"""


def _lock_runs(keys: str) -> str:
    return f"""
    PERFORM 1 FROM workflow_run_status_counts
    WHERE status IN ({keys}) ORDER BY status FOR UPDATE;
"""


_RUNS_OLD_KEYS = "SELECT status::text FROM old_rows"
_RUNS_ALL_KEYS = "SELECT status::text FROM old_rows UNION SELECT status::text FROM new_rows"


_ROLLUP_FUNCTIONS = {
    "token_usage_totals_on_insert": _TOKENS_ADD,
    "token_usage_totals_on_delete": _lock_tokens(_TOKENS_OLD_KEYS) + _TOKENS_SUBTRACT,
    "token_usage_totals_on_update": _lock_tokens(_TOKENS_ALL_KEYS) + _TOKENS_SUBTRACT + _TOKENS_ADD,
    "token_usage_totals_on_truncate": "DELETE FROM token_usage_model_totals;",
    "workflow_run_counts_on_insert": _RUNS_ADD,
    "workflow_run_counts_on_delete": _lock_runs(_RUNS_OLD_KEYS) + _RUNS_SUBTRACT,
    "workflow_run_counts_on_update": _lock_runs(_RUNS_ALL_KEYS) + _RUNS_SUBTRACT + _RUNS_ADD,
    "workflow_run_counts_on_truncate": "DELETE FROM workflow_run_status_counts;",
}

_NEW = "NEW TABLE AS new_rows"
_OLD = "OLD TABLE AS old_rows"
_ROLLUP_TRIGGERS = [
    # (trigger, table, event, transition tables, function)
    ("trg_token_usage_totals_ins", "token_usage", "INSERT", _NEW, "token_usage_totals_on_insert"),
    ("trg_token_usage_totals_del", "token_usage", "DELETE", _OLD, "token_usage_totals_on_delete"),
    (
        "trg_token_usage_totals_upd",
        "token_usage",
        "UPDATE",
        f"{_OLD} {_NEW}",
        "token_usage_totals_on_update",
    ),
    (
        "trg_token_usage_totals_trunc",
        "token_usage",
        "TRUNCATE",
        None,
        "token_usage_totals_on_truncate",
    ),
    (
        "trg_workflow_run_counts_ins",
        "workflow_runs",
        "INSERT",
        _NEW,
        "workflow_run_counts_on_insert",
    ),
    (
        "trg_workflow_run_counts_del",
        "workflow_runs",
        "DELETE",
        _OLD,
        "workflow_run_counts_on_delete",
    ),
    (
        "trg_workflow_run_counts_upd",
        "workflow_runs",
        "UPDATE",
        f"{_OLD} {_NEW}",
        "workflow_run_counts_on_update",
    ),
    (
        "trg_workflow_run_counts_trunc",
        "workflow_runs",
        "TRUNCATE",
        None,
        "workflow_run_counts_on_truncate",
    ),
]


def upgrade() -> None:
    # 1. Runtime role.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anveksha_app') THEN
                CREATE ROLE anveksha_app LOGIN;
            END IF;
        END $$;
    """)

    # 2. Tables.
    op.create_table(
        "admin_console_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("total_users", sa.Integer(), nullable=False),
        sa.Column("active_candidates", sa.Integer(), nullable=False),
        sa.Column("active_verifiers", sa.Integer(), nullable=False),
        sa.Column("active_companies", sa.Integer(), nullable=False),
        sa.Column("sessions_today", sa.Integer(), nullable=False),
        sa.Column("reports_this_week", sa.Integer(), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("activity", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("months", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("sessions", sa.ARRAY(sa.Integer()), nullable=False),
        sa.Column("top_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("top_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "admin_feature_flags",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("scope", sa.String(9), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope IN ('global', 'candidate', 'verifier', 'company')",
            name="admin_feature_flag_scope",
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "admin_role_permissions",
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("permissions", sa.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('candidate', 'company', 'interviewer', 'hr', 'admin')", name="user_role_value"
        ),
        sa.PrimaryKeyConstraint("role"),
    )
    op.create_table(
        "admin_slots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("verifier", sa.String(length=200), nullable=False),
        sa.Column("day", sa.String(length=20), nullable=False),
        sa.Column("time", sa.String(length=20), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("skill", sa.String(length=120), nullable=False),
        sa.Column("booked", sa.Boolean(), nullable=False),
        sa.Column("candidate", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ai_models",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(13), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "cost_per_1k_in", sa.Numeric(precision=12, scale=6, asdecimal=False), nullable=False
        ),
        sa.Column(
            "cost_per_1k_out", sa.Numeric(precision=12, scale=6, asdecimal=False), nullable=False
        ),
        sa.Column("fallback_id", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('Anthropic', 'OpenAI', 'Azure OpenAI', 'Google Vertex', 'AWS Bedrock', 'Custom')",
            name="ai_model_provider",
        ),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ai_model_status"),
        sa.ForeignKeyConstraint(["fallback_id"], ["ai_models.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_models_created_at", "ai_models", ["created_at"], unique=False)
    op.create_index(op.f("ix_ai_models_fallback_id"), "ai_models", ["fallback_id"], unique=False)
    op.create_index(op.f("ix_ai_models_model"), "ai_models", ["model"], unique=False)
    op.create_index(op.f("ix_ai_models_status"), "ai_models", ["status"], unique=False)
    op.create_table(
        "anonymous_interviewers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("specialties", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("external_sessions", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "assessments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(10), nullable=False),
        sa.Column("depth", sa.String(12), nullable=False),
        sa.Column("type", sa.String(12), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("available", sa.Integer(), nullable=False),
        sa.Column("popular", sa.Boolean(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("probes", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "depth IN ('Foundational', 'Intermediate', 'Advanced', 'Expert', 'Staff')",
            name="assessment_depth",
        ),
        sa.CheckConstraint(
            "domain IN ('Backend', 'Frontend', 'Data', 'Payments', 'Cloud', 'Platform', 'Leadership', 'Behavioral')",
            name="assessment_domain",
        ),
        sa.CheckConstraint("type IN ('live', 'bot', 'bot-assisted')", name="assessment_type"),
        sa.CheckConstraint("duration > 0", name="ck_assessments_duration_pos"),
        sa.CheckConstraint("price >= 0", name="ck_assessments_price_nonneg"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assessments_published"), "assessments", ["published"], unique=False)
    op.create_index(op.f("ix_assessments_slug"), "assessments", ["slug"], unique=True)
    op.create_table(
        "billing",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("plan", sa.String(10), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("seats_used", sa.Integer(), nullable=False),
        sa.Column("monthly_amount", sa.Integer(), nullable=False),
        sa.Column("next_billing", sa.String(length=40), nullable=False),
        sa.Column("includes", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("ai_chats_used", sa.Integer(), nullable=False),
        sa.Column("ai_chats_included", sa.Integer(), nullable=False),
        sa.Column("invoices", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("plan IN ('Starter', 'Growth', 'Enterprise')", name="billing_plan"),
        sa.CheckConstraint("seats_used <= seats", name="ck_billing_seats_used_le_seats"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "booking_catalogs",
        sa.Column("catalog_id", sa.String(), nullable=False),
        sa.Column("skill_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("depth", sa.String(length=60), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("style", sa.String(length=120), nullable=False),
        sa.Column("format", sa.String(length=120), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("probes", sa.Text(), nullable=False),
        sa.Column("week_range", sa.String(length=60), nullable=False),
        sa.Column("days", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("slots", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("catalog_id"),
    )
    op.create_table(
        "companies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("primary_domain", sa.String(length=200), nullable=False),
        sa.Column("credit_balance", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("credit_balance >= 0", name="ck_companies_credit_balance_nonneg"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "coupons",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(7), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("desc", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("type <> 'percent' OR value <= 100", name="ck_coupons_percent_max"),
        sa.CheckConstraint("type IN ('percent', 'fixed')", name="coupon_type"),
        sa.CheckConstraint("value > 0", name="ck_coupons_value_pos"),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "credit_rate",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "rupees_per_credit", sa.Numeric(precision=10, scale=4, asdecimal=False), nullable=False
        ),
        sa.Column("rate_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "flag_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "followup_skills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("requested", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "integrity_flags",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("ref_id", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(9), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('high', 'medium', 'confirmed')", name="integrity_severity"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "interviewer_approvals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("candidate_name", sa.String(length=200), nullable=False),
        sa.Column("candidate_initials", sa.String(length=4), nullable=False),
        sa.Column("dossier_id", sa.String(length=40), nullable=False),
        sa.Column("requested_skill", sa.String(length=200), nullable=False),
        sa.Column("origin", sa.String(14), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("candidate_score", sa.Float(), nullable=True),
        sa.Column("candidate_sessions", sa.Integer(), nullable=True),
        sa.Column("bot_reasoning", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "origin IN ('bot-discovered', 'self-requested')", name="approval_origin"
        ),
        sa.CheckConstraint(
            "status = 'pending' OR reviewed_at IS NOT NULL",
            name="ck_interviewer_approvals_decided_reviewed_at",
        ),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="approval_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_interviewer_approvals_candidate_id"),
        "interviewer_approvals",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_interviewer_approvals_decided",
        "interviewer_approvals",
        ["reviewed_at", "id"],
        unique=False,
        postgresql_where=sa.text("status <> 'pending'"),
    )
    op.create_index(
        op.f("ix_interviewer_approvals_status"), "interviewer_approvals", ["status"], unique=False
    )
    op.create_index(
        "uq_interviewer_approvals_pending_skill",
        "interviewer_approvals",
        ["candidate_id", "requested_skill"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "model_credentials",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("additional_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("provider"),
    )
    op.create_table(
        "onboarding_steps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pending_reports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("candidate", sa.String(length=200), nullable=False),
        sa.Column("initials", sa.String(length=4), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("date", sa.String(length=40), nullable=False),
        sa.Column("ai_score", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pilot_programs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("college", sa.String(length=200), nullable=False),
        sa.Column("dept", sa.String(length=200), nullable=False),
        sa.Column("batch", sa.String(length=40), nullable=False),
        sa.Column("coordinator", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("students", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("avg_score", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.String(length=40), nullable=False),
        sa.Column("end_date", sa.String(length=40), nullable=False),
        sa.Column("assessments", sa.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'draft', 'completed')", name="pilot_program_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pilot_students",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("program", sa.String(length=40), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("pending", sa.Integer(), nullable=False),
        sa.Column("avg_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'registered')", name="pilot_student_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pilot_students_program"), "pilot_students", ["program"], unique=False)
    op.create_table(
        "rbac_audit",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("time", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rbac_custom_roles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_role", sa.String(9), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("members", sa.Integer(), nullable=False),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "base_role IN ('candidate', 'verifier', 'company', 'admin')",
            name="rbac_custom_role_base",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rbac_roles",
        sa.Column("id", sa.String(9), nullable=False),
        sa.Column("order_seq", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("color", sa.String(length=60), nullable=False),
        sa.Column("perms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "id IN ('candidate', 'verifier', 'company', 'admin')", name="rbac_role_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "search_candidates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("initials", sa.String(length=4), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("years", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=False),
        sa.Column("verification_score", sa.Integer(), nullable=False),
        sa.Column("match_percent", sa.Integer(), nullable=False),
        sa.Column("verified_skills", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("gray_skills", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("last_activity", sa.String(length=60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "match_percent BETWEEN 0 AND 100", name="ck_search_candidates_match_percent"
        ),
        sa.CheckConstraint(
            "verification_score BETWEEN 0 AND 100", name="ck_search_candidates_verification_score"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_candidates_verification_score",
        "search_candidates",
        ["verification_score"],
        unique=False,
    )
    op.create_table(
        "search_facets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("locations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "specialist_invites",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("skill_name", sa.String(length=200), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_by", sa.String(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_proofs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('sent', 'accepted', 'expired')", name="invite_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(14), nullable=False),
        sa.Column("pipelines", sa.Integer(), nullable=False),
        sa.Column("last_active", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('Hiring Manager', 'Recruiter', 'Viewer')", name="team_role"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="team_member_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "token_usage_model_totals",
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("requests", sa.BigInteger(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=18, scale=6, asdecimal=False), nullable=False),
        sa.PrimaryKeyConstraint("model_name"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("user_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picture", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "verifier_console_state",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("candidate", sa.String(length=200), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("prioritized_probes", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("gray_requested", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("reliability", sa.Integer(), nullable=False),
        sa.Column("score_variance", sa.Float(), nullable=False),
        sa.Column("candidate_rating", sa.Float(), nullable=False),
        sa.Column("appeal_rate", sa.Float(), nullable=False),
        sa.Column("average_review_time_min", sa.Integer(), nullable=False),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recent_reports", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_month", sa.String(length=40), nullable=False),
        sa.Column("current_amount", sa.Integer(), nullable=False),
        sa.Column("current_sessions", sa.Integer(), nullable=False),
        sa.Column("ytd_amount", sa.Integer(), nullable=False),
        sa.Column("ytd_sessions", sa.Integer(), nullable=False),
        sa.Column("rate_standard", sa.Integer(), nullable=False),
        sa.Column("rate_advanced", sa.Integer(), nullable=False),
        sa.Column("pending", sa.Integer(), nullable=False),
        sa.Column("months", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rate_card", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("years_experience", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("linkedin", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=60), nullable=False),
        sa.Column("specializations", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("pending_reports", sa.Integer(), nullable=False),
        sa.Column("quality", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "verifier_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("lane", sa.String(9), nullable=False),
        sa.Column("raw_id", sa.String(), nullable=False),
        sa.Column("time", sa.String(length=20), nullable=False),
        sa.Column("date", sa.String(length=40), nullable=False),
        sa.Column("candidate", sa.String(length=200), nullable=False),
        sa.Column("candidate_initials", sa.String(length=4), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("depth", sa.String(length=60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lane IN ('live', 'upcoming', 'completed')", name="verifier_session_lane"
        ),
        sa.CheckConstraint(
            "status IN ('live', 'scheduled', 'completed')", name="verifier_session_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_verifier_sessions_lane"), "verifier_sessions", ["lane"], unique=False)
    op.create_table(
        "verifier_slots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("day", sa.String(3), nullable=False),
        sa.Column("time", sa.String(length=20), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("booked", sa.Boolean(), nullable=False),
        sa.Column("candidate", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("day IN ('Mon', 'Tue', 'Wed', 'Thu', 'Fri')", name="verifier_slot_day"),
        sa.CheckConstraint("duration IN (30, 60, 90)", name="verifier_slot_duration"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "verifier_suggested_gaps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sub", sa.Text(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workflow_run_status_counts",
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("runs", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("status"),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')", name="workflow_run_status"
        ),
        sa.PrimaryKeyConstraint("workflow_id"),
    )
    op.create_index(
        "ix_workflow_runs_status_started_at",
        "workflow_runs",
        ["status", "started_at"],
        unique=False,
    )
    op.create_table(
        "active_interviewers",
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("candidate_name", sa.String(length=200), nullable=False),
        sa.Column("candidate_initials", sa.String(length=4), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("reliability", sa.Integer(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authorities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("mode IN ('freelance', 'specialist')", name="active_interviewer_mode"),
        sa.ForeignKeyConstraint(["candidate_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_table(
        "admin_candidates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("linked_user_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=False),
        sa.Column("verifications", sa.Integer(), nullable=False),
        sa.Column("top_score", sa.Integer(), nullable=False),
        sa.Column("last_session", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(11), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'blacklisted')", name="admin_candidate_status"),
        sa.ForeignKeyConstraint(
            ["linked_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_admin_candidates_linked_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_candidates_linked_user_id"),
        "admin_candidates",
        ["linked_user_id"],
        unique=False,
    )
    op.create_table(
        "admin_companies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("linked_company_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("plan", sa.String(10), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("seats_used", sa.Integer(), nullable=False),
        sa.Column("chats", sa.Integer(), nullable=False),
        sa.Column("followups", sa.Integer(), nullable=False),
        sa.Column("since", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(7), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "plan IN ('Starter', 'Growth', 'Enterprise')", name="admin_company_plan"
        ),
        sa.CheckConstraint("status IN ('active', 'trial', 'churned')", name="admin_company_status"),
        sa.ForeignKeyConstraint(
            ["linked_company_id"],
            ["companies.id"],
            ondelete="SET NULL",
            name="fk_admin_companies_linked_company_id_companies",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_companies_linked_company_id"),
        "admin_companies",
        ["linked_company_id"],
        unique=False,
    )
    op.create_table(
        "admin_verifiers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("linked_user_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("specialization", sa.String(length=200), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("quality", sa.String(9), nullable=False),
        sa.Column("since", sa.String(length=20), nullable=False),
        sa.Column("tier", sa.String(10), nullable=False),
        sa.Column("experience", sa.String(length=200), nullable=True),
        sa.Column("applied", sa.String(length=20), nullable=True),
        sa.Column("sample", sa.String(8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quality IN ('Exemplary', 'Strong', 'Probation')", name="admin_verifier_quality"
        ),
        sa.CheckConstraint("sample IN ('Reviewed', 'Pending')", name="admin_verifier_sample"),
        sa.CheckConstraint(
            "tier IN ('active', 'applicants', 'probation')", name="admin_verifier_tier"
        ),
        sa.ForeignKeyConstraint(
            ["linked_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_admin_verifiers_linked_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_verifiers_linked_user_id"),
        "admin_verifiers",
        ["linked_user_id"],
        unique=False,
    )
    op.create_table(
        "agent_registry",
        sa.Column("id", sa.String(17), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("used_by", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("system_message", sa.Text(), nullable=False),
        sa.Column("default_system_message", sa.Text(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "id IN ('interviewer_brief', 'report_generator', 'gap_analyzer', 'gray_analyzer', 'candidate_search', 'candidate_chat')",
            name="agent_registry_id",
        ),
        sa.ForeignKeyConstraint(["model_id"], ["ai_models.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_registry_enabled"), "agent_registry", ["enabled"], unique=False)
    op.create_index(
        op.f("ix_agent_registry_model_id"), "agent_registry", ["model_id"], unique=False
    )
    op.create_table(
        "bots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("sessions_run", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("avatar", sa.String(length=4), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("specializations", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("primary_model_id", sa.String(), nullable=True),
        sa.Column("fallback_model_id", sa.String(), nullable=True),
        sa.Column("persona", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("avg_score", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("bot_type", sa.String(11), nullable=True),
        sa.Column("avg_rating", sa.Float(), nullable=True),
        sa.Column("model_label", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("bot_type IN ('interviewer', 'reviewer', 'co-pilot')", name="bot_type"),
        sa.CheckConstraint(
            "status IN ('active', 'draft', 'inactive', 'paused')", name="bot_status"
        ),
        sa.ForeignKeyConstraint(["fallback_model_id"], ["ai_models.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["primary_model_id"], ["ai_models.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bots_created_at", "bots", ["created_at"], unique=False)
    op.create_index(op.f("ix_bots_fallback_model_id"), "bots", ["fallback_model_id"], unique=False)
    op.create_index(op.f("ix_bots_primary_model_id"), "bots", ["primary_model_id"], unique=False)
    op.create_table(
        "company_unlocks",
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["search_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(6), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("interviewer_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('earned', 'spent')", name="credit_tx_kind"),
        sa.ForeignKeyConstraint(
            ["interviewer_id"], ["anonymous_interviewers.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_credit_transactions_at"), "credit_transactions", ["at"], unique=False)
    op.create_index(
        op.f("ix_credit_transactions_interviewer_id"),
        "credit_transactions",
        ["interviewer_id"],
        unique=False,
    )
    op.create_index(
        "ix_credit_transactions_kind_at", "credit_transactions", ["kind", "at"], unique=False
    )
    op.create_table(
        "flag_defs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("default", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["flag_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_flag_defs_group_id"), "flag_defs", ["group_id"], unique=False)
    op.create_table(
        "followup_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("skills", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["search_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_followup_requests_candidate_id"),
        "followup_requests",
        ["candidate_id"],
        unique=False,
    )
    op.create_table(
        "gray_followups",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("candidate", sa.String(length=200), nullable=False),
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("gray_area", sa.String(length=200), nullable=False),
        sa.Column("asked", sa.Integer(), nullable=False),
        sa.Column("requested", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("companies", sa.Text(), nullable=True),
        sa.Column("scheduled", sa.String(length=60), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'requested', 'accepted', 'completed', 'declined')",
            name="gray_followup_status",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["search_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_gray_followups_candidate_id"), "gray_followups", ["candidate_id"], unique=False
    )
    op.create_table(
        "insights",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(9), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("cta", sa.String(length=60), nullable=False),
        sa.Column("companies", sa.Integer(), nullable=True),
        sa.Column("acted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('follow-up', 'gap', 'momentum', 'integrity')", name="insight_kind"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_insights_user_id"), "insights", ["user_id"], unique=False)
    op.create_table(
        "live_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("catalog_id", sa.String(), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(5), nullable=False),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=False),
        sa.Column("candidate_name", sa.String(length=200), nullable=False),
        sa.Column("candidate_initials", sa.String(length=4), nullable=False),
        sa.Column("candidate_color", sa.String(length=20), nullable=False),
        sa.Column("verifier_name", sa.String(length=200), nullable=False),
        sa.Column("verifier_initials", sa.String(length=4), nullable=False),
        sa.Column("verifier_color", sa.String(length=20), nullable=False),
        sa.Column("current_probe", sa.Text(), nullable=False),
        sa.Column("suggested_probes", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("unverified_claim_text", sa.Text(), nullable=True),
        sa.Column("unverified_claim_at", sa.String(length=20), nullable=True),
        sa.Column("transcript", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("phases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assessment", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('live', 'ended')", name="live_session_status"),
        sa.ForeignKeyConstraint(
            ["catalog_id"],
            ["booking_catalogs.catalog_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_live_sessions_catalog_id"), "live_sessions", ["catalog_id"], unique=False
    )
    op.create_table(
        "my_interviews",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("catalog_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("scheduled_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('scheduled', 'completed')", name="my_interview_status"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_my_interviews_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_my_interviews_user_id"), "my_interviews", ["user_id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(9), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.Column("href", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('session', 'dossier', 'company', 'followup', 'integrity')",
            name="notification_kind",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_id_created_at",
        "notifications",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "pipeline_cards",
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("initials", sa.String(length=4), nullable=False),
        sa.Column("match_percent", sa.Integer(), nullable=False),
        sa.Column("last_activity", sa.String(length=60), nullable=False),
        sa.Column("stage", sa.String(13), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IN ('investigating', 'followup', 'shortlist', 'offered')", name="pipeline_stage"
        ),
        sa.CheckConstraint(
            "match_percent BETWEEN 0 AND 100", name="ck_pipeline_cards_match_percent"
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["search_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_table(
        "privacy_settings",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("share_profile", sa.Boolean(), nullable=False),
        sa.Column("share_dossiers", sa.Boolean(), nullable=False),
        sa.Column("share_transcripts", sa.Boolean(), nullable=False),
        sa.Column("allow_gray_followups", sa.Boolean(), nullable=False),
        sa.Column("hide_from_companies", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("discoverability", sa.String(13), nullable=False),
        sa.Column("share_score", sa.Boolean(), nullable=False),
        sa.Column("share_gap", sa.Boolean(), nullable=False),
        sa.Column("share_gray", sa.Boolean(), nullable=False),
        sa.Column("share_transcript", sa.Boolean(), nullable=False),
        sa.Column("allow_followup", sa.Boolean(), nullable=False),
        sa.Column("anonymous_mode", sa.Boolean(), nullable=False),
        sa.Column("share_verifier_panel", sa.Boolean(), nullable=False),
        sa.Column("shared_reports", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "discoverability IN ('anyone', 'verified-only', 'invite-only', 'private')",
            name="privacy_discoverability",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "public_profiles",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("share_url", sa.Text(), nullable=False),
        sa.Column("anv_id", sa.String(length=40), nullable=False),
        sa.Column("last_updated", sa.String(length=40), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("unique_companies", sa.Integer(), nullable=False),
        sa.Column("inbound_chats", sa.Integer(), nullable=False),
        sa.Column("about", sa.Text(), nullable=False),
        sa.Column("highlights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("constellation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timeline", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gray_areas", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "skill_ledgers",
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("candidate_name", sa.String(length=200), nullable=False),
        sa.Column("candidate_title", sa.String(length=200), nullable=False),
        sa.Column("candidate_location", sa.String(length=120), nullable=False),
        sa.Column("candidate_initials", sa.String(length=4), nullable=False),
        sa.Column("dossier_id", sa.String(length=40), nullable=False),
        sa.Column("verification_score", sa.Float(), nullable=False),
        sa.Column("verified_count", sa.Integer(), nullable=False),
        sa.Column("partial_count", sa.Integer(), nullable=False),
        sa.Column("gray_count", sa.Integer(), nullable=False),
        sa.Column("top_percent", sa.Integer(), nullable=False),
        sa.Column("profile_bio", sa.Text(), nullable=True),
        sa.Column("profile_current_role", sa.String(length=200), nullable=True),
        sa.Column("profile_experience_years", sa.Integer(), nullable=True),
        sa.Column("profile_skills", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("interviewer_mode", sa.String(10), nullable=False),
        sa.Column("interviewer_origin", sa.String(14), nullable=True),
        sa.Column("interviewer_approved_by", sa.String(), nullable=True),
        sa.Column("interviewer_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interviewer_bio", sa.Text(), nullable=True),
        sa.Column("stats_sessions", sa.Integer(), nullable=True),
        sa.Column("stats_rating", sa.Float(), nullable=True),
        sa.Column("stats_reliability", sa.Integer(), nullable=True),
        sa.Column("stats_peer_score", sa.Integer(), nullable=True),
        sa.Column("stats_appeal_rate", sa.Float(), nullable=True),
        sa.Column("stats_average_review_minutes", sa.Integer(), nullable=True),
        sa.Column("stats_monthly_earnings", sa.Integer(), nullable=True),
        sa.Column("external_proofs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "interviewer_mode IN ('none', 'pending', 'freelance', 'specialist')",
            name="interviewer_mode",
        ),
        sa.CheckConstraint(
            "interviewer_origin IN ('bot-discovered', 'self-requested', 'admin-invited')",
            name="interviewer_origin",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_table(
        "skill_report_details",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(length=40), nullable=False),
        sa.Column("assessment_title", sa.String(length=200), nullable=False),
        sa.Column("candidate_name", sa.String(length=200), nullable=False),
        sa.Column("candidate_ext_id", sa.String(length=40), nullable=False),
        sa.Column("verifier_name", sa.String(length=200), nullable=False),
        sa.Column("verifier_ext_id", sa.String(length=40), nullable=False),
        sa.Column("verifier_title", sa.String(length=200), nullable=False),
        sa.Column("verifier_rating", sa.Float(), nullable=False),
        sa.Column("date", sa.String(length=40), nullable=False),
        sa.Column("duration", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(12), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("depth", sa.String(length=60), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("verdict_long", sa.Text(), nullable=False),
        sa.Column("summary", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("fit_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("phases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gray", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("type IN ('live', 'bot', 'bot-assisted')", name="report_detail_type"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_skill_report_details_user_id"), "skill_report_details", ["user_id"], unique=False
    )
    op.create_table(
        "token_usage",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("orchestration_type", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("input_cost", sa.Numeric(precision=12, scale=6, asdecimal=False), nullable=False),
        sa.Column(
            "output_cost", sa.Numeric(precision=12, scale=6, asdecimal=False), nullable=False
        ),
        sa.Column("total_cost", sa.Numeric(precision=12, scale=6, asdecimal=False), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("interview_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "orchestration_type IN ('direct', 'group_chat', 'round_robin', 'workflow', 'hierarchical')",
            name="token_usage_orchestration_type",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL", name="fk_token_usage_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(op.f("ix_token_usage_created_at"), "token_usage", ["created_at"], unique=False)
    op.create_index(
        "ix_token_usage_model_name_created_at",
        "token_usage",
        ["model_name", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_token_usage_user_id"), "token_usage", ["user_id"], unique=False)
    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(11), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "role IN ('candidate', 'company', 'interviewer', 'hr', 'admin')", name="user_role_value"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role", name="uq_user_roles_user_id_role"),
    )
    op.create_index(op.f("ix_user_roles_role"), "user_roles", ["role"], unique=False)
    op.create_table(
        "admin_dossiers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("report_id", sa.String(), nullable=True),
        sa.Column("candidate", sa.String(length=200), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("verifier", sa.String(length=200), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('published', 'in-review', 'draft', 'archived')", name="admin_dossier_status"
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["skill_report_details.id"],
            ondelete="SET NULL",
            name="fk_admin_dossiers_report_id_skill_report_details",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_dossiers_report_id"), "admin_dossiers", ["report_id"], unique=False
    )
    op.create_table(
        "assessment_bots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assessment_id", sa.String(), nullable=False),
        sa.Column("bot_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "bot_id", name="uq_assessment_bot"),
    )
    op.create_index(op.f("ix_assessment_bots_bot_id"), "assessment_bots", ["bot_id"], unique=False)
    op.create_table(
        "dossiers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("candidate_name", sa.String(length=200), nullable=False),
        sa.Column("candidate_initials", sa.String(length=4), nullable=False),
        sa.Column("candidate_title", sa.String(length=200), nullable=False),
        sa.Column("candidate_location", sa.String(length=120), nullable=False),
        sa.Column("years", sa.Integer(), nullable=False),
        sa.Column("verification_score", sa.Float(), nullable=False),
        sa.Column("gray_areas", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("strengths", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["skill_ledgers.candidate_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id"),
    )
    op.create_table(
        "flag_state",
        sa.Column("flag_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["flag_id"], ["flag_defs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("flag_id"),
    )
    op.create_table(
        "interviewer_authorities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ledger_candidate_id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(length=40), nullable=False),
        sa.Column("skill_name", sa.String(length=200), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ledger_candidate_id"], ["skill_ledgers.candidate_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_candidate_id", "skill_name", name="uq_authority_ledger_skill"),
    )
    op.create_table(
        "session_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("report_id", sa.String(), nullable=True),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("date", sa.String(length=40), nullable=False),
        sa.Column("duration", sa.String(length=40), nullable=False),
        sa.Column("verifier", sa.String(length=200), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('published', 'archived', 'in-review')", name="session_history_status"
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["skill_report_details.id"],
            ondelete="SET NULL",
            name="fk_session_history_report_id_skill_report_details",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_session_history_report_id"), "session_history", ["report_id"], unique=False
    )
    op.create_index(
        "ix_session_history_user_id_created_at",
        "session_history",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "session_reports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("candidate_name", sa.String(length=200), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("verdict", sa.String(8), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("gray_areas", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("strengths", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("report_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_report_id", sa.String(), nullable=True),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'review', 'published')", name="session_report_status"
        ),
        sa.CheckConstraint(
            "verdict IN ('verified', 'partial', 'gray')", name="session_report_verdict"
        ),
        sa.ForeignKeyConstraint(
            ["published_report_id"],
            ["skill_report_details.id"],
            ondelete="SET NULL",
            name="fk_session_reports_published_report_id_skill_report_details",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_session_reports_published_report_id"),
        "session_reports",
        ["published_report_id"],
        unique=False,
    )
    op.create_index(op.f("ix_session_reports_status"), "session_reports", ["status"], unique=False)
    op.create_table(
        "skill_ledger_rows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ledger_candidate_id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("depth", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("last_verified", sa.String(length=20), nullable=True),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.String(length=40), nullable=True),
        sa.Column("authority", sa.Boolean(), nullable=True),
        sa.Column("authority_since", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('verified', 'partial', 'gray', 'claimed')", name="skill_state"
        ),
        sa.ForeignKeyConstraint(
            ["ledger_candidate_id"], ["skill_ledgers.candidate_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_candidate_id", "skill_id", name="uq_ledger_skill_id"),
    )
    op.create_table(
        "skill_reports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("report_id", sa.String(), nullable=True),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("verifier", sa.String(length=200), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("companies_viewed", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('published', 'in-review', 'draft')", name="skill_report_status"
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["skill_report_details.id"],
            ondelete="SET NULL",
            name="fk_skill_reports_report_id_skill_report_details",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_skill_reports_report_id"), "skill_reports", ["report_id"], unique=False
    )
    op.create_index(op.f("ix_skill_reports_user_id"), "skill_reports", ["user_id"], unique=False)
    op.create_table(
        "token_usage_agent_ids",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_usage_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["token_usage_id"], ["token_usage.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_token_usage_agent_ids_agent_id"),
        "token_usage_agent_ids",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_token_usage_agent_ids_token_usage_id"),
        "token_usage_agent_ids",
        ["token_usage_id"],
        unique=False,
    )
    op.create_table(
        "dossier_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dossier_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(length=40), nullable=False),
        sa.Column("date", sa.String(length=40), nullable=False),
        sa.Column("skill", sa.String(length=200), nullable=False),
        sa.Column("verifier", sa.String(length=200), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.CheckConstraint("verdict IN ('verified', 'unverified')", name="dossier_session_verdict"),
        sa.ForeignKeyConstraint(["dossier_id"], ["dossiers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_dossier_sessions_dossier_id"), "dossier_sessions", ["dossier_id"], unique=False
    )

    # 3. updated_at triggers.
    op.execute(_function("set_updated_at", "NEW.updated_at = now();", returns="NEW"))
    op.execute("""
        DO $$ DECLARE t text; BEGIN
            FOR t IN SELECT table_name FROM information_schema.columns
                     WHERE table_schema = 'public' AND column_name = 'updated_at'
            LOOP
                EXECUTE format('CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON %I '
                               'FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t);
            END LOOP;
        END $$;
    """)

    # 4. Rollup triggers.
    for name, body in _ROLLUP_FUNCTIONS.items():
        op.execute(_function(name, body))
    for trigger, table, event, transition, function in _ROLLUP_TRIGGERS:
        referencing = f"REFERENCING {transition} " if transition else ""
        op.execute(
            f"CREATE TRIGGER {trigger} AFTER {event} ON {table} {referencing}"
            f"FOR EACH STATEMENT EXECUTE FUNCTION {function}();"
        )

    # 5. Grants.
    op.execute("GRANT USAGE ON SCHEMA public TO anveksha_app;")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anveksha_app;"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anveksha_app;")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anveksha_app;"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO anveksha_app;"
    )

    # 6. Row-level security on every table, alembic_version included.
    op.execute("""
        DO $$ DECLARE t text; BEGIN
            FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
                EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
                EXECUTE format('CREATE POLICY anveksha_app_all ON %I TO anveksha_app '
                               'USING (true) WITH CHECK (true)', t);
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS anveksha_app_all ON alembic_version;")
    op.execute("ALTER TABLE alembic_version DISABLE ROW LEVEL SECURITY;")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM anveksha_app;"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM anveksha_app;"
    )
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM anveksha_app;")
    op.execute("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anveksha_app;")
    op.execute("REVOKE USAGE ON SCHEMA public FROM anveksha_app;")

    # Dropping a table drops its triggers and policy too.
    op.drop_index(op.f("ix_dossier_sessions_dossier_id"), table_name="dossier_sessions")
    op.drop_table("dossier_sessions")
    op.drop_index(
        op.f("ix_token_usage_agent_ids_token_usage_id"), table_name="token_usage_agent_ids"
    )
    op.drop_index(op.f("ix_token_usage_agent_ids_agent_id"), table_name="token_usage_agent_ids")
    op.drop_table("token_usage_agent_ids")
    op.drop_index(op.f("ix_skill_reports_user_id"), table_name="skill_reports")
    op.drop_index(op.f("ix_skill_reports_report_id"), table_name="skill_reports")
    op.drop_table("skill_reports")
    op.drop_table("skill_ledger_rows")
    op.drop_index(op.f("ix_session_reports_status"), table_name="session_reports")
    op.drop_index(op.f("ix_session_reports_published_report_id"), table_name="session_reports")
    op.drop_table("session_reports")
    op.drop_index("ix_session_history_user_id_created_at", table_name="session_history")
    op.drop_index(op.f("ix_session_history_report_id"), table_name="session_history")
    op.drop_table("session_history")
    op.drop_table("interviewer_authorities")
    op.drop_table("flag_state")
    op.drop_table("dossiers")
    op.drop_index(op.f("ix_assessment_bots_bot_id"), table_name="assessment_bots")
    op.drop_table("assessment_bots")
    op.drop_index(op.f("ix_admin_dossiers_report_id"), table_name="admin_dossiers")
    op.drop_table("admin_dossiers")
    op.drop_index(op.f("ix_user_roles_role"), table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_index(op.f("ix_token_usage_user_id"), table_name="token_usage")
    op.drop_index("ix_token_usage_model_name_created_at", table_name="token_usage")
    op.drop_index(op.f("ix_token_usage_created_at"), table_name="token_usage")
    op.drop_table("token_usage")
    op.drop_index(op.f("ix_skill_report_details_user_id"), table_name="skill_report_details")
    op.drop_table("skill_report_details")
    op.drop_table("skill_ledgers")
    op.drop_table("public_profiles")
    op.drop_table("privacy_settings")
    op.drop_table("pipeline_cards")
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_my_interviews_user_id"), table_name="my_interviews")
    op.drop_table("my_interviews")
    op.drop_index(op.f("ix_live_sessions_catalog_id"), table_name="live_sessions")
    op.drop_table("live_sessions")
    op.drop_index(op.f("ix_insights_user_id"), table_name="insights")
    op.drop_table("insights")
    op.drop_index(op.f("ix_gray_followups_candidate_id"), table_name="gray_followups")
    op.drop_table("gray_followups")
    op.drop_index(op.f("ix_followup_requests_candidate_id"), table_name="followup_requests")
    op.drop_table("followup_requests")
    op.drop_index(op.f("ix_flag_defs_group_id"), table_name="flag_defs")
    op.drop_table("flag_defs")
    op.drop_index("ix_credit_transactions_kind_at", table_name="credit_transactions")
    op.drop_index(op.f("ix_credit_transactions_interviewer_id"), table_name="credit_transactions")
    op.drop_index(op.f("ix_credit_transactions_at"), table_name="credit_transactions")
    op.drop_table("credit_transactions")
    op.drop_table("company_unlocks")
    op.drop_index(op.f("ix_bots_primary_model_id"), table_name="bots")
    op.drop_index(op.f("ix_bots_fallback_model_id"), table_name="bots")
    op.drop_index("ix_bots_created_at", table_name="bots")
    op.drop_table("bots")
    op.drop_index(op.f("ix_agent_registry_model_id"), table_name="agent_registry")
    op.drop_index(op.f("ix_agent_registry_enabled"), table_name="agent_registry")
    op.drop_table("agent_registry")
    op.drop_index(op.f("ix_admin_verifiers_linked_user_id"), table_name="admin_verifiers")
    op.drop_table("admin_verifiers")
    op.drop_index(op.f("ix_admin_companies_linked_company_id"), table_name="admin_companies")
    op.drop_table("admin_companies")
    op.drop_index(op.f("ix_admin_candidates_linked_user_id"), table_name="admin_candidates")
    op.drop_table("admin_candidates")
    op.drop_table("active_interviewers")
    op.drop_index("ix_workflow_runs_status_started_at", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflow_run_status_counts")
    op.drop_table("verifier_suggested_gaps")
    op.drop_table("verifier_slots")
    op.drop_index(op.f("ix_verifier_sessions_lane"), table_name="verifier_sessions")
    op.drop_table("verifier_sessions")
    op.drop_table("verifier_console_state")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_table("users")
    op.drop_table("token_usage_model_totals")
    op.drop_table("team_members")
    op.drop_table("specialist_invites")
    op.drop_table("search_facets")
    op.drop_index("ix_search_candidates_verification_score", table_name="search_candidates")
    op.drop_table("search_candidates")
    op.drop_table("rbac_roles")
    op.drop_table("rbac_custom_roles")
    op.drop_table("rbac_audit")
    op.drop_index(op.f("ix_pilot_students_program"), table_name="pilot_students")
    op.drop_table("pilot_students")
    op.drop_table("pilot_programs")
    op.drop_table("pending_reports")
    op.drop_table("onboarding_steps")
    op.drop_table("model_credentials")
    op.drop_index(
        "uq_interviewer_approvals_pending_skill",
        table_name="interviewer_approvals",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(op.f("ix_interviewer_approvals_status"), table_name="interviewer_approvals")
    op.drop_index(
        "ix_interviewer_approvals_decided",
        table_name="interviewer_approvals",
        postgresql_where=sa.text("status <> 'pending'"),
    )
    op.drop_index(op.f("ix_interviewer_approvals_candidate_id"), table_name="interviewer_approvals")
    op.drop_table("interviewer_approvals")
    op.drop_table("integrity_flags")
    op.drop_table("followup_skills")
    op.drop_table("flag_groups")
    op.drop_table("credit_rate")
    op.drop_table("coupons")
    op.drop_table("companies")
    op.drop_table("booking_catalogs")
    op.drop_table("billing")
    op.drop_index(op.f("ix_assessments_slug"), table_name="assessments")
    op.drop_index(op.f("ix_assessments_published"), table_name="assessments")
    op.drop_table("assessments")
    op.drop_table("anonymous_interviewers")
    op.drop_index(op.f("ix_ai_models_status"), table_name="ai_models")
    op.drop_index(op.f("ix_ai_models_model"), table_name="ai_models")
    op.drop_index(op.f("ix_ai_models_fallback_id"), table_name="ai_models")
    op.drop_index("ix_ai_models_created_at", table_name="ai_models")
    op.drop_table("ai_models")
    op.drop_table("admin_slots")
    op.drop_table("admin_role_permissions")
    op.drop_table("admin_feature_flags")
    op.drop_table("admin_console_snapshots")

    for name in [*_ROLLUP_FUNCTIONS, "set_updated_at"]:
        op.execute(f"DROP FUNCTION IF EXISTS {name}();")
    # Enum types created along with the tables.
    op.execute("""
        DO $$ DECLARE t text; BEGIN
            FOR t IN SELECT typname FROM pg_type
                     WHERE typnamespace = 'public'::regnamespace AND typtype = 'e'
            LOOP
                EXECUTE format('DROP TYPE %I', t);
            END LOOP;
        END $$;
    """)
    # The anveksha_app role stays: dropping a live login role out from under
    # a running app is worse than leaving an unused one behind.
