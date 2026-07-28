from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from households.models import Household


class DiscussionTopicQuerySet(models.QuerySet):
    def available_to(self, user):
        return self.filter(household__memberships__user=user)


class DiscussionTopic(models.Model):
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="discussion_topics"
    )
    title = models.CharField(max_length=180)
    notes = models.TextField(blank=True, default="")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_discussion_topics",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="completed_discussion_topics",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reminder_claimed_at = models.DateTimeField(null=True, blank=True)
    reminder_processed_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    objects = DiscussionTopicQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(
                fields=["household", "is_done", "-updated_at"],
                name="talk_later_pending_idx",
            ),
            models.Index(
                fields=[
                    "is_done",
                    "scheduled_for",
                    "reminder_processed_at",
                    "reminder_claimed_at",
                ],
                name="talk_later_due_idx",
            ),
            models.Index(
                fields=["household", "is_done", "scheduled_for"],
                name="talk_later_upcoming_idx",
            ),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        self.title = self.title.strip()
        self.notes = self.notes.strip()
        if not self.title:
            raise ValidationError({"title": "Enter a topic title."})

    def save(self, *args, **kwargs):
        self.title = self.title.strip()
        self.notes = self.notes.strip()
        if not self.title:
            raise ValidationError({"title": "Enter a topic title."})
        if self.pk:
            previous_schedule = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("scheduled_for", flat=True)
                .first()
            )
            if previous_schedule != self.scheduled_for:
                self.reminder_claimed_at = None
                self.reminder_processed_at = None
                self.reminder_sent_at = None
                update_fields = kwargs.get("update_fields")
                if update_fields is not None:
                    kwargs["update_fields"] = set(update_fields) | {
                        "reminder_claimed_at",
                        "reminder_processed_at",
                        "reminder_sent_at",
                    }
        return super().save(*args, **kwargs)
