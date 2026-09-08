from django.db import migrations

from apps.core.dbguards import immutable_columns_v1

TARGETS = {"projects_project": ("organization_id",), "projects_environment": ("project_id", "kind"),
           "projects_apiservice": ("environment_id", "audience")}


def forwards(apps, schema_editor):
    for table, columns in TARGETS.items():
        immutable_columns_v1(schema_editor, table, columns)


def backwards(apps, schema_editor):
    for table, columns in TARGETS.items():
        immutable_columns_v1(schema_editor, table, columns, remove=True)


class Migration(migrations.Migration):
    dependencies = [("projects", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
