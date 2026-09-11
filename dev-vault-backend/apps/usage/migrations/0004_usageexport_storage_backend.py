from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("usage", "0003_fact_guards")]
    operations = [migrations.AddField(
        model_name="usageexport", name="storage_backend",
        field=models.CharField(choices=[("local", "Local"), ("s3", "S3")], default="local", max_length=8),
    )]
