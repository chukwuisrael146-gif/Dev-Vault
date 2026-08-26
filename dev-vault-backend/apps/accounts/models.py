from typing import Any

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.managers import UserManager
from apps.core.models import BaseModel


class User(AbstractUser, BaseModel):
    """DevVault human identity; authentication workflows are added in the Accounts step."""

    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ("email",)
        verbose_name = "user"
        verbose_name_plural = "users"

    def clean(self) -> None:
        super().clean()
        self.email = UserManager.normalize_email_address(self.email)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = UserManager.normalize_email_address(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email
