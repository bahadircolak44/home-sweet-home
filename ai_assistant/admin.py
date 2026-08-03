from django.contrib import admin

from .models import AssistantCommand


@admin.register(AssistantCommand)
class AssistantCommandAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "household",
        "source",
        "status",
        "action_type",
        "created_at",
        "expires_at",
        "executed_at",
    )
    list_filter = ("source", "status", "action_type", "created_at")
    search_fields = ("id", "user__username")
    readonly_fields = (
        "id",
        "request_id",
        "user",
        "household",
        "source",
        "transcript",
        "status",
        "action_type",
        "proposal",
        "user_message",
        "result_url",
        "result_label",
        "created_at",
        "expires_at",
        "executed_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False
