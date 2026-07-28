import argparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from talk_later.models import DiscussionTopic


class Command(BaseCommand):
    help = "Synchronize existing Talk Later topics with Google Calendar."

    def add_arguments(self, parser):
        parser.add_argument("--user", metavar="USERNAME")
        parser.add_argument("--household", metavar="HOUSEHOLD_ID", type=int)
        parser.add_argument(
            "--future-only",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Synchronize only future topics (default: true).",
        )
        parser.add_argument("--limit", type=int)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Also synchronize topics already marked as synced.",
        )

    def handle(self, *args, **options):
        if not settings.GOOGLE_CALENDAR_ENABLED:
            raise CommandError("Google Calendar integration is not enabled.")
        if options["limit"] is not None and options["limit"] <= 0:
            raise CommandError("--limit must be a positive integer.")

        topics = DiscussionTopic.objects.filter(scheduled_for__isnull=False).order_by(
            "scheduled_for", "pk"
        )
        if options["future_only"]:
            topics = topics.filter(scheduled_for__gt=timezone.now(), is_done=False)
        if options["user"]:
            topics = topics.filter(created_by__username=options["user"])
        if options["household"] is not None:
            topics = topics.filter(household_id=options["household"])
        if not options["force"]:
            topics = topics.exclude(
                calendar_sync_status=DiscussionTopic.CalendarSyncStatus.SYNCED
            )
        if options["limit"] is not None:
            topics = topics[: options["limit"]]

        from google_integration.services import sync_topic_calendar_event

        processed = synced = failed = reconnect_required = 0
        for topic in topics:
            processed += 1
            sync_topic_calendar_event(topic)
            topic.refresh_from_db(fields=["calendar_sync_status"])
            if topic.calendar_sync_status == topic.CalendarSyncStatus.SYNCED:
                synced += 1
            elif topic.calendar_sync_status == topic.CalendarSyncStatus.REAUTHORIZATION_REQUIRED:
                reconnect_required += 1
            else:
                failed += 1
        self.stdout.write(
            "Processed {processed}; synced {synced}; failed {failed}; reconnect required {reconnect_required}.".format(
                processed=processed,
                synced=synced,
                failed=failed,
                reconnect_required=reconnect_required,
            )
        )
