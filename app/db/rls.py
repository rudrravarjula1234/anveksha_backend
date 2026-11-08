"""Row-level security setup shared by migrations.

Every table in `public` has RLS enabled with one permissive policy for
`anveksha_app`, the runtime role (see migration 0001): it keeps
Supabase's Data API (`anon` / `authenticated`) out while the app sees
every row. Table owners (migrations, tests) bypass RLS.

A migration that creates a table calls `op.execute(enable_rls_sql("t"))`;
`tests/test_db_invariants.py::test_every_public_table_has_rls` fails if one
is missed.
"""


def enable_rls_sql(table: str) -> str:
    """SQL that enables RLS on `table` and (re)creates the app policy when
    the `anveksha_app` role exists. `table` must be a trusted identifier."""
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        DO $$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anveksha_app') THEN
                DROP POLICY IF EXISTS anveksha_app_all ON {table};
                CREATE POLICY anveksha_app_all ON {table}
                    TO anveksha_app USING (true) WITH CHECK (true);
            END IF;
        END $$;
    """
