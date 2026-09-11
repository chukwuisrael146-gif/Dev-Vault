from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audit", "0005_append_only_guard")]
    operations = [migrations.AddField(
        model_name="auditexport", name="storage_backend",
        field=models.CharField(choices=[("local", "Local"), ("s3", "S3")], default="local", max_length=8),
    )]
