from io import StringIO
from smtplib import SMTPAuthenticationError
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError

from config.email import development_mailer


@pytest.fixture
def smtp():
    return {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": "smtp.example.test",
            "port": 587,
            "username": "fixture",
            "password": "fixture-secret",
            "use_tls": True,
            "use_ssl": False,
        },
    }


def test_file_mode_remains_explicitly_local(smtp, tmp_path):
    mailer = development_mailer(mode="file", smtp_mailer=smtp, base_dir=tmp_path)
    assert mailer["BACKEND"].endswith("filebased.EmailBackend")
    assert mailer["OPTIONS"]["file_path"] == tmp_path / "var" / "emails"


def test_smtp_mode_preserves_sender_configuration(smtp, tmp_path):
    mailer = development_mailer(mode="smtp", smtp_mailer=smtp, base_dir=tmp_path)
    assert mailer == smtp
    mailer["OPTIONS"]["password"] = "changed"
    assert smtp["OPTIONS"]["password"] == "fixture-secret"


@pytest.mark.parametrize(
    "mode,changes",
    [
        ("invalid", {}),
        ("smtp", {"use_ssl": True}),
        ("smtp", {"use_tls": False}),
        ("smtp", {"password": ""}),
    ],
)
def test_invalid_email_configuration_fails_without_secrets(mode, changes, smtp, tmp_path):
    smtp["OPTIONS"].update(changes)
    with pytest.raises(ImproperlyConfigured) as error:
        development_mailer(mode=mode, smtp_mailer=smtp, base_dir=tmp_path)
    assert "fixture-secret" not in str(error.value)


def test_connection_check_does_not_send_mail(settings, smtp):
    settings.MAILERS = {"default": smtp}
    connection = Mock()
    output = StringIO()
    with patch("django.core.mail.mailers.create_connection", return_value=connection):
        call_command("check_email_connection", stdout=output)
    connection.open.assert_called_once()
    connection.close.assert_called_once()
    connection.send_messages.assert_not_called()
    assert "No email was sent" in output.getvalue()


def test_connection_check_hides_provider_error_details(settings, smtp):
    settings.MAILERS = {"default": smtp}
    connection = Mock()
    connection.open.side_effect = SMTPAuthenticationError(535, b"fixture-secret")
    with (
        patch("django.core.mail.mailers.create_connection", return_value=connection),
        pytest.raises(CommandError) as error,
    ):
        call_command("check_email_connection")
    assert "SMTPAuthenticationError" in str(error.value)
    assert "fixture-secret" not in str(error.value)
    connection.close.assert_called_once()


def test_connection_check_rejects_local_file_delivery(settings):
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.filebased.EmailBackend"}}
    with pytest.raises(CommandError, match="SMTP is not enabled"):
        call_command("check_email_connection")


def test_watch_processes_both_queues_and_stops_cleanly():
    module = "apps.accounts.management.commands.deliver_account_emails"
    output = StringIO()
    with (
        patch(f"{module}.deliver_pending_verification_emails", return_value=1) as verify,
        patch(f"{module}.deliver_pending_password_resets", return_value=1) as reset,
        patch(f"{module}.close_old_connections"),
        patch(f"{module}.time.sleep", side_effect=KeyboardInterrupt),
    ):
        call_command("deliver_account_emails", watch=True, stdout=output)
    verify.assert_called_once()
    reset.assert_called_once()
    assert "1 verification and 1 reset" in output.getvalue()
    assert "stopped" in output.getvalue()


def test_worker_rejects_invalid_polling_interval():
    with pytest.raises(CommandError, match="between 1 and 60"):
        call_command("deliver_account_emails", interval=0)
