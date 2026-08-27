from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import RefreshTokenSession, User


@admin.register(User)
class DevVaultUserAdmin(UserAdmin):
    ordering = ("email",)
        
    list_display = (
        'email',
        'status',
        'email_is_verified',
        'is_staff',
        'is_active',
        'created_at',
    )
    list_filter = ('status', 'is_staff', 'is_active')
    search_fields = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (
            _('Account'),
            {
                "fields": (
                    'status',
                    'email_verified_at',
                    'is_active',
                )
            },
        ),
        (_('Personal info'), {'fields': ('first_name', 'last_name')}),
        (
            _('Permissions'),
            {
                'fields': (
                    'is_staff',
                    'is_superuser',
                    'groups',
                    'user_permissions',
                    
                )
            },
        ),
        (
            _('Important dates'),
            {
                'fields': (
                        'last_login',
                        'date_joined',
                        'created_at',
                        'updated_at',
                )
            },
        ),
    )
    
    readonly_fields = (
        'email_verified_at',
        'created_at',
        'updated_at',
    )
    
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email',
                    'password1',
                    'password2',
                    'status',
                    'is_staff',
                    'is_active',
                ),
            },
        ),
    )
    
@admin.register(RefreshTokenSession)
class RefreshTokenSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'expires_at',
        'revoked_at',
        'last_used_at',
        'created_at',
    )
    list_filter = ('revoked_at',)
    search_fields = ('user__email', 'token_jti')
    readonly_fields = (
        'id',
        'user',
        'token_jti',
        'expires_at',
        'revoked_at',
        'last_used_at',
        'created_ip_address',
        'user_agent',
        'created_at',
        'updated_at',
    )
    
    def has_add_permission(self, request) -> bool:
        return False
    
    def has_change_permission(self, request, obj=None) -> bool:
        return False
    
    def has_delete_permission(self, request, obj=None) -> bool:
        return False