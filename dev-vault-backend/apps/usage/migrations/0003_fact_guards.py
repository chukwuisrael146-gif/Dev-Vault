from django.db import migrations

from apps.core.dbguards import append_only_v1


def forwards(apps, schema_editor):
    for table in ("usage_usageevent", "usage_quotareservation"):
        append_only_v1(schema_editor, table)


def backwards(apps, schema_editor):
    for table in ("usage_usageevent", "usage_quotareservation"):
        append_only_v1(schema_editor, table, remove=True)


class Migration(migrations.Migration):
    dependencies = [("usage", "0002_usageexport")]
    operations = [migrations.RunPython(forwards, backwards)]
