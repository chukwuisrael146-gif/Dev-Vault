from django.db import migrations

from apps.core.dbguards import append_only_v1


def forwards(apps, schema_editor):
    append_only_v1(schema_editor, "audit_auditlog")


def backwards(apps, schema_editor):
    append_only_v1(schema_editor, "audit_auditlog", remove=True)


class Migration(migrations.Migration):
    dependencies = [("audit", "0004_auditexport_auditlog_actor_type_auditlog_source_ip")]
    operations = [migrations.RunPython(forwards, backwards)]
