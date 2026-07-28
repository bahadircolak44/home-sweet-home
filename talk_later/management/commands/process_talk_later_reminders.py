from django.core.management.base import BaseCommand, CommandError

from talk_later.services import DEFAULT_REMINDER_BATCH_LIMIT, process_due_reminders


class Command(BaseCommand):
    help = "Process due Talk Later reminders once."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_REMINDER_BATCH_LIMIT,
            help="Maximum due topics to process (1-100).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= DEFAULT_REMINDER_BATCH_LIMIT:
            raise CommandError("--limit must be between 1 and 100.")
        counts = process_due_reminders(limit=limit)
        self.stdout.write(
            "claimed={claimed} processed={processed} sent={sent} "
            "no_subscription={no_subscription} failed={failed}".format(**counts)
        )
