from django.db import migrations

from apps.core.dbguards import append_only_v1


def forwards(apps, schema_editor):
    append_only_v1(schema_editor, "webhooks_deliveryattempt")


def backwards(apps, schema_editor):
    append_only_v1(schema_editor, "webhooks_deliveryattempt", remove=True)


class Migration(migrations.Migration):
    dependencies = [("webhooks", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
