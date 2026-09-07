"""Opt-in integration settings for a dedicated PostgreSQL server, never the dev DB."""

from config.settings.test import *

DATABASES = {"default": env.db("TEST_DATABASE_URL")}
DATABASES["default"]["TEST"] = {"NAME": "test_devvault_email_verification"}
