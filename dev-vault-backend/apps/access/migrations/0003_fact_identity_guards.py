from django.db import migrations

from apps.core.dbguards import append_only_v1, immutable_columns_v1

FACTS = ("access_policyrevision", "access_quotaadjustment", "access_quotanotice")
IDENTITIES = {"access_permission": ("service_id", "name"),
              "access_policy": ("organization_id", "environment_kind", "project_id", "service_id", "key_family_id", "algorithm", "dimension")}


def forwards(apps, schema_editor):
    for table in FACTS:
        append_only_v1(schema_editor, table)
    for table, columns in IDENTITIES.items():
        immutable_columns_v1(schema_editor, table, columns)
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            CREATE FUNCTION devvault_grant_boundary_v1() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM credentials_apikey k JOIN access_permission p
                    ON p.service_id = k.service_id WHERE k.id=NEW.key_id AND p.id=NEW.permission_id) THEN
                    RAISE EXCEPTION 'Scope grants cannot cross service boundaries' USING ERRCODE='23514';
                END IF;
                RETURN NEW;
            END $$;
            CREATE TRIGGER access_grant_boundary BEFORE INSERT OR UPDATE ON access_apikeypermission
                FOR EACH ROW EXECUTE FUNCTION devvault_grant_boundary_v1();
        """)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER IF EXISTS access_grant_boundary ON access_apikeypermission; DROP FUNCTION IF EXISTS devvault_grant_boundary_v1();")
    for table in FACTS:
        append_only_v1(schema_editor, table, remove=True)
    for table, columns in IDENTITIES.items():
        immutable_columns_v1(schema_editor, table, columns, remove=True)


class Migration(migrations.Migration):
    dependencies = [("access", "0002_quotanotice"), ("credentials", "0002_apikey_family_id")]
    operations = [migrations.RunPython(forwards, backwards)]
