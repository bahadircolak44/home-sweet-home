from django.contrib import admin

from .models import PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "endpoint_host",
        "last_activity_at",
        "last_notified_at",
        "created_at",
        "updated_at",
    )
    list_filter = ("created_at", "updated_at")
    search_fields = ("user__username",)
    readonly_fields = (
        "endpoint_host",
        "user_agent",
        "created_at",
        "updated_at",
        "last_seen_at",
        "last_activity_at",
        "last_notified_at",
    )
    fields = (
        "user",
        "endpoint_host",
        "user_agent",
        "last_activity_at",
        "last_notified_at",
        "created_at",
        "updated_at",
        "last_seen_at",
    )
    list_select_related = ("user",)

    @admin.display(description="Endpoint host")
    def endpoint_host(self, subscription):
        return subscription.endpoint_host
