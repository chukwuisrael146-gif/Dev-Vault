import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create a local PostgreSQL custom-format backup without putting passwords "
        "in command arguments."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pg-bin", default=r"C:\Program Files\PostgreSQL\18\bin" if os.name == "nt" else ""
        )

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if database["ENGINE"] != "django.db.backends.postgresql":
            raise CommandError("This command requires PostgreSQL.")
        binary = (
            str(Path(options["pg_bin"]) / "pg_dump.exe")
            if options["pg_bin"]
            else shutil.which("pg_dump")
        )
        if not binary or not Path(binary).is_file():
            raise CommandError("pg_dump was not found; specify --pg-bin.")
        directory = settings.BASE_DIR / "var" / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"devvault-{uuid4().hex}.dump"
        child_env = os.environ.copy()
        child_env["PGPASSWORD"] = database.get("PASSWORD", "")
        child_env["PGCONNECT_TIMEOUT"] = "10"
        arguments = [
            binary,
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--file",
            str(destination),
            "--host",
            database.get("HOST") or "127.0.0.1",
            "--port",
            str(database.get("PORT") or 5432),
            "--username",
            database.get("USER") or "",
            "--dbname",
            database["NAME"],
        ]
        result = subprocess.run(
            arguments,
            env=child_env,
            capture_output=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            check=False,
        )
        if result.returncode:
            destination.unlink(missing_ok=True)
            raise CommandError(
                "Backup failed; check database connectivity and pg_dump compatibility. "
                "Credentials were not logged."
            )
        self.stdout.write(self.style.SUCCESS(f"Backup created: {destination}"))
        self.stdout.write(
            "This file contains private database data. It is ignored by Git; "
            "store production backups encrypted off-host."
        )
