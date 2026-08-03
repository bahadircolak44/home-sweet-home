from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ai_assistant.models import AssistantCommand


class Command(BaseCommand):
    help = "Delete old terminal AI assistant command records."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-days", type=int, default=30)

    def handle(self, *args, **options):
        days = options["older_than_days"]
        if days < 0:
            raise CommandError("--older-than-days must be zero or greater.")
        terminal_statuses = [
            AssistantCommand.Status.EXECUTED,
            AssistantCommand.Status.CANCELLED,
            AssistantCommand.Status.UNRESOLVED,
            AssistantCommand.Status.FAILED,
            AssistantCommand.Status.EXPIRED,
        ]
        deleted, _ = AssistantCommand.objects.filter(
            status__in=terminal_statuses,
            created_at__lt=timezone.now() - timedelta(days=days),
        ).delete()
        self.stdout.write(f"Deleted {deleted} AI assistant command records.")
