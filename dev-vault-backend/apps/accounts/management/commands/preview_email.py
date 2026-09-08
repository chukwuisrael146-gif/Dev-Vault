"""Decode local MIME mail; never copy quoted-printable links from raw .log files."""

import re
import webbrowser
from email import policy
from email.parser import BytesParser
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Decode the newest local email; --open opens its account link. Development only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--open",
            action="store_true",
            help="Open the link in your browser, without printing it.",
        )

    def handle(self, *args, **options):
        backend = settings.MAILERS["default"]["BACKEND"]
        if backend != "django.core.mail.backends.filebased.EmailBackend":
            raise CommandError("Email preview requires the local file-based development mailer.")
        folder = (settings.BASE_DIR / "var" / "emails").resolve()
        files = [p for p in folder.glob("*.log") if p.is_file() and not p.is_symlink()]
        if not files:
            raise CommandError("No local email found. Run deliver_account_emails first.")
        latest = max(files, key=lambda p: p.stat().st_mtime_ns)
        message = BytesParser(policy=policy.default).parsebytes(latest.read_bytes())
        part = message.get_body(preferencelist=("plain",)) if message.is_multipart() else message
        body = part.get_content()
        if not options["open"]:
            self.stdout.write(
                "Private development email: do not share or commit the following link."
            )
            self.stdout.write(body)
            return
        match = re.search(r"https?://[^\s<>]+", body)
        if not match:
            raise CommandError("No account link found in the newest email.")
        link = urlsplit(match.group())
        origin = urlsplit(settings.ACCOUNT_PUBLIC_BASE_URL)
        if (link.scheme, link.netloc) != (origin.scheme, origin.netloc) or link.path not in {
            "/api/v1/auth/verify-email/",
            "/api/v1/auth/password-reset/confirm/",
        }:
            raise CommandError("The email link does not match this project's account URL.")
        if not webbrowser.open(match.group()):
            raise CommandError(
                "Could not open a browser. Run without --open to inspect the decoded email."
            )
        self.stdout.write(
            "Opened the newest account email link. Complete the action in your browser."
        )
