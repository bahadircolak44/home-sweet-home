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
        "calendar_sync_status",
        "calendar_synced_at",
        "created_at",
    )
    list_filter = (
        "is_done",
        "household",
        "scheduled_for",
        "calendar_sync_status",
        "created_at",
    )
    search_fields = ("title", "notes", "household__name", "created_by__username")
    autocomplete_fields = ("household", "created_by", "completed_by")
    readonly_fields = (
        "created_at",
        "updated_at",
        "completed_at",
        "reminder_claimed_at",
        "reminder_processed_at",
        "reminder_sent_at",
        "google_calendar_event_id",
        "google_calendar_html_link",
        "google_calendar_id",
        "calendar_sync_status",
        "calendar_last_attempt_at",
        "calendar_synced_at",
    )
    ordering = ("is_done", "scheduled_for", "-updated_at")
