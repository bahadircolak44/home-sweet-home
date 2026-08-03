import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from households.models import Household


class AssistantCommand(models.Model):
    class Source(models.TextChoices):
        TEXT = "TEXT", "Text"
        AUDIO = "AUDIO", "Audio"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION", "Needs confirmation"
        UNRESOLVED = "UNRESOLVED", "Unresolved"
        EXECUTED = "EXECUTED", "Executed"
        CANCELLED = "CANCELLED", "Cancelled"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"

    class ActionType(models.TextChoices):
        ADD_GROCERY_ITEM = "ADD_GROCERY_ITEM", "Add grocery item"
        ADD_CHORE_TASK = "ADD_CHORE_TASK", "Add chore task"
        ADD_TALK_LATER_TOPIC = "ADD_TALK_LATER_TOPIC", "Add Talk Later topic"
        NONE = "NONE", "None"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_commands",
    )
    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="assistant_commands",
    )
    source = models.CharField(max_length=8, choices=Source.choices)
    transcript = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    action_type = models.CharField(
        max_length=24, choices=ActionType.choices, default=ActionType.NONE
    )
    proposal = models.JSONField(default=dict, blank=True)
    user_message = models.TextField(blank=True, default="")
    result_url = models.CharField(max_length=500, blank=True, default="")
    result_label = models.CharField(max_length=600, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "status", "-created_at"],
                name="ai_command_user_status_idx",
            ),
            models.Index(fields=["expires_at"], name="ai_command_expiry_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "household", "request_id"],
                name="ai_command_user_household_request",
            )
        ]

    def clean(self):
        super().clean()
        self.transcript = self.transcript.strip()
        self.user_message = self.user_message.strip()
        if len(self.transcript) > 1000:
            raise ValidationError({"transcript": "Transcript must be 1,000 characters or fewer."})
        if len(self.user_message) > 1000:
            raise ValidationError({"user_message": "Message must be 1,000 characters or fewer."})
        if self.status != self.Status.RECEIVED and not self.transcript:
            raise ValidationError({"transcript": "A completed command requires a transcript."})

    def __str__(self):
        return f"Assistant command {self.pk}"
