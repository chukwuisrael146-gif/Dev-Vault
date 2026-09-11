"""Opt-in browser smoke test: isolated Django database, no personal browser profile."""

import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.accounts.models import RefreshTokenSession, User
from apps.credentials.models import APIKey
from apps.organizations.models import Organization
from apps.projects.models import Project


@pytest.mark.skipif(
    os.environ.get("DEVVAULT_BROWSER_TEST") != "1",
    reason="Requires frontend dependencies and Microsoft Edge; opt in explicitly.",
)
@pytest.mark.django_db(transaction=True)
def test_browser_to_django_workspace(live_server, settings):
    if connection.vendor != "postgresql":
        pytest.skip("Browser concurrency requires PostgreSQL; use scripts/test_postgresql.ps1.")
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
    cache.clear()
    password = secrets.token_urlsafe(32)
    user = User.objects.create_user(
        email="browser-smoke@example.test",
        password=password,
        email_verified_at=timezone.now(),
    )
    frontend = Path(__file__).resolve().parents[4] / "dev-vault-frontend"
    node = shutil.which("node")
    assert node, "Install Node.js before running the browser integration check."
    environment = {
        **os.environ,
        "DEVVAULT_E2E_BACKEND_URL": live_server.url,
        "DEVVAULT_E2E_EMAIL": user.email,
        "DEVVAULT_E2E_PASSWORD": password,
    }
    try:
        result = subprocess.run(
            [node, "tests/real-backend-smoke.mjs"],
            cwd=frontend,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        organization = Organization.objects.get(slug="browser-smoke")
        assert Project.objects.filter(organization=organization, slug="browser-project").exists()
        assert APIKey.objects.filter(
            name="Browser integration key", revoked_at__isnull=False
        ).exists()
        assert not RefreshTokenSession.objects.filter(user=user, revoked_at__isnull=True).exists()
    finally:
        cache.clear()
