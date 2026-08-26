from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


@admin.register(User)
class DevVaultUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "is_staff", "is_active", "created_at")
    search_fields = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (
            _("Important dates"),
            {"fields": ("last_login", "date_joined", "created_at", "updated_at")},
        ),
    )
    readonly_fields = ("created_at", "updated_at")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )
