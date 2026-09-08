"""Versioned PostgreSQL migration helpers. Never change v1 semantics after release."""


def append_only_v1(schema_editor, table, *, remove=False):
    if schema_editor.connection.vendor != "postgresql":
        return
    quoted = schema_editor.quote_name(table)
    trigger = schema_editor.quote_name(f"{table}_append_only")
    if remove:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {quoted}")
        return
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION devvault_reject_fact_mutation_v1() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'DevVault facts are append-only' USING ERRCODE = '23514';
        END $$
    """)
    schema_editor.execute(
        f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {quoted} "
        "FOR EACH ROW EXECUTE FUNCTION devvault_reject_fact_mutation_v1()"
    )


def immutable_columns_v1(schema_editor, table, columns, *, remove=False):
    if schema_editor.connection.vendor != "postgresql":
        return
    quoted = schema_editor.quote_name(table)
    trigger = schema_editor.quote_name(f"{table}_immutable_identity")
    if remove:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {quoted}")
        return
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION devvault_immutable_identity_v1() RETURNS trigger
        LANGUAGE plpgsql AS $$ DECLARE i integer; BEGIN
            FOR i IN 0..TG_NARGS-1 LOOP
                IF (to_jsonb(OLD)->TG_ARGV[i]) IS DISTINCT FROM (to_jsonb(NEW)->TG_ARGV[i]) THEN
                    RAISE EXCEPTION 'DevVault parent/identity is immutable' USING ERRCODE = '23514';
                END IF;
            END LOOP;
            RETURN NEW;
        END $$
    """)
    # Columns are hard-coded migration identifiers, never runtime/user input.
    arguments = ", ".join("'" + column + "'" for column in columns)
    schema_editor.execute(
        f"CREATE TRIGGER {trigger} BEFORE UPDATE ON {quoted} "
        f"FOR EACH ROW EXECUTE FUNCTION devvault_immutable_identity_v1({arguments})"
    )
