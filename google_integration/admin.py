from django.contrib import admin

from .models import GoogleAccountConnection


@admin.register(GoogleAccountConnection)
class GoogleAccountConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "email",
        "connected_at",
        "last_login_at",
        "last_calendar_success_at",
        "reauthorization_required",
    )
    list_filter = ("email_verified", "reauthorization_required")
    search_fields = ("user__username", "user__email", "email")
    readonly_fields = (
        "google_subject",
        "email",
        "email_verified",
        "granted_scopes",
        "connected_at",
        "updated_at",
        "last_login_at",
        "last_calendar_success_at",
        "reauthorization_required",
        "last_error",
    )
    exclude = ("encrypted_refresh_token",)
    list_select_related = ("user",)
