from urllib.parse import urlparse

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models


class PushSubscription(models.Model):
    """A browser-specific Web Push subscription owned by one authenticated user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.TextField(unique=True, validators=[MaxLengthValidator(2048)])
    p256dh = models.TextField(validators=[MaxLengthValidator(512)])
    auth = models.TextField(validators=[MaxLengthValidator(256)])
    user_agent = models.TextField(blank=True, validators=[MaxLengthValidator(500)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField()
    last_notified_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "-updated_at"])]

    @property
    def endpoint_host(self):
        """Return only a short host label suitable for non-sensitive UI."""
        host = urlparse(self.endpoint).hostname or "Unknown host"
        return host[:120]

    def __str__(self):
        return f"{self.user.get_username()} on {self.endpoint_host}"


class ReleaseAnnouncement(models.Model):
    """An idempotency record for a deployment-wide Web Push announcement."""

    release_id = models.CharField(max_length=128, unique=True)
    notes = models.TextField()
    attempted_subscription_count = models.PositiveIntegerField(default=0)
    successful_delivery_count = models.PositiveIntegerField(default=0)
    announced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.release_id
