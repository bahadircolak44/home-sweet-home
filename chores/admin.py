from django.contrib import admin

from .models import ChoreSession, ChoreTask, ChoreTemplate


@admin.register(ChoreSession)
class ChoreSessionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "household",
        "status",
        "created_by",
        "completed_by",
        "updated_at",
    )
    list_filter = ("status", "household", "created_at", "completed_at")
    search_fields = ("name", "notes", "household__name", "created_by__username")
    autocomplete_fields = ("household", "created_by", "completed_by")
    readonly_fields = ("created_at", "updated_at", "completed_at")


@admin.register(ChoreTask)
class ChoreTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "session",
        "assignee",
        "is_done",
        "completed_by",
        "created_at",
    )
    list_filter = ("is_done", "session", "session__household", "created_at")
    search_fields = ("title", "session__name", "assignee__username")
    autocomplete_fields = (
        "session",
        "assignee",
        "source_template",
        "created_by",
        "completed_by",
    )
    readonly_fields = ("created_at", "updated_at", "completed_at")


@admin.register(ChoreTemplate)
class ChoreTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "household",
        "default_assignee",
        "is_active",
        "created_by",
        "updated_at",
    )
    list_filter = ("is_active", "household", "created_at")
    search_fields = ("title", "household__name", "default_assignee__username")
    autocomplete_fields = ("household", "default_assignee", "created_by")
    readonly_fields = ("created_at", "updated_at")
