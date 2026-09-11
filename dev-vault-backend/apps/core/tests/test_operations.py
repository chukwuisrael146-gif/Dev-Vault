from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.core.exports import export_path
from apps.projects.tests.test_projects import resources  # noqa: F401
from apps.usage.models import UsageAggregate, UsageExport
from apps.usage.services import aggregate_pending


@pytest.mark.django_db(transaction=True)
def test_reconciliation_empty_and_corrupt_aggregate(resources):
    from apps.usage.tests.test_reporting import event

    _, _, _, _, service = resources
    event(service)
    call_command("reconcile_usage", stdout=StringIO())
    aggregate_pending()
    call_command("reconcile_usage", stdout=StringIO())
    UsageAggregate.objects.update(units=999)
    with pytest.raises(CommandError, match="reconciliation failed"):
        call_command("reconcile_usage", stdout=StringIO())
    assert UsageAggregate.objects.get().units == 999


@pytest.mark.django_db
def test_expired_exports_cleanup_is_explicit_and_preserves_sources(settings, tmp_path):
    settings.EXPORT_ROOT = tmp_path
    job = UsageExport.objects.create(
        organization_id=uuid4(),
        actor_id=uuid4(),
        filters={},
        status="ready",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    file_path = export_path(job)
    # The export writer is the implementation's file-writing path, not a test secret fixture.
    with patch("apps.core.management.commands.cleanup_exports.delete_export") as candidate:
        call_command("cleanup_exports", stdout=StringIO())
        candidate.assert_not_called()
        call_command("cleanup_exports", apply=True, stdout=StringIO())
        candidate.assert_called_once()
    job.refresh_from_db()
    assert job.status == "expired" and UsageExport.objects.count() == 1
    assert file_path.parent == tmp_path.resolve()
    with patch("pathlib.Path.is_symlink", return_value=True), pytest.raises(ValueError):
        export_path(job)


def test_backup_rejects_non_postgresql():
    with (
        patch("apps.core.management.commands.backup_database.settings") as configuration,
        pytest.raises(CommandError, match="requires PostgreSQL"),
    ):
        configuration.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3"}}
        call_command("backup_database", stdout=StringIO())


def test_gunicorn_explicit_handlers_and_no_raw_access_logger():
    import runpy
    from pathlib import Path

    configuration = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "docker/gunicorn.conf.py")
    )
    logging_config = configuration["logconfig_dict"]
    for logger in logging_config["loggers"].values():
        assert set(logger["handlers"]) <= set(logging_config["handlers"])
    access = logging_config["loggers"]["gunicorn.access"]
    assert access["handlers"] == ["discard"] and not access["propagate"]
    configuration["child_exit"](None, type("Worker", (), {"pid": 123})())
