import pytest
from django.db import IntegrityError, connection, transaction

from apps.audit.models import AuditLog
from apps.projects.models import Project
from apps.projects.tests.test_projects import resources  # noqa: F401

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL database guards"),
]


def test_audit_cannot_be_modified_with_raw_sql(resources):
    record = AuditLog.objects.first()
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE audit_auditlog SET outcome = 'tampered' WHERE id = %s", [record.id])
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM audit_auditlog WHERE id = %s", [record.id])


def test_project_parent_cannot_be_changed_by_direct_orm_update(resources):
    from uuid import uuid4

    project = resources[2]
    with pytest.raises(IntegrityError), transaction.atomic():
        Project.objects.filter(pk=project.id).update(organization_id=uuid4())
