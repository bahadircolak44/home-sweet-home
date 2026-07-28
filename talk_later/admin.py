from django.contrib import admin

from .models import DiscussionTopic


@admin.register(DiscussionTopic)
class DiscussionTopicAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "household",
        "scheduled_for",
        "is_done",
        "created_by",
        "completed_by",
        "reminder_processed_at",
        "reminder_sent_at",
        "created_at",
    )
    list_filter = ("is_done", "household", "scheduled_for", "created_at")
    search_fields = ("title", "notes", "household__name", "created_by__username")
    autocomplete_fields = ("household", "created_by", "completed_by")
    readonly_fields = (
        "created_at",
        "updated_at",
        "completed_at",
        "reminder_claimed_at",
        "reminder_processed_at",
        "reminder_sent_at",
    )
    ordering = ("is_done", "scheduled_for", "-updated_at")
