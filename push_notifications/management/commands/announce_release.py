import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from push_notifications.release_notes import ReleaseNotesError, release_notes_for_deployment
from push_notifications.services import announce_release


class Command(BaseCommand):
    help = "Send the prepared release notes to every subscribed device once."

    def add_arguments(self, parser):
        parser.add_argument("--release-id", required=True)
        parser.add_argument("--notes-file", default="RELEASE_NOTES.md")

    def handle(self, *args, **options):
        release_id = options["release_id"].strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{7,128}", release_id):
            raise CommandError("--release-id must be a safe deployment identifier.")
        if not settings.PUSH_NOTIFICATIONS_ENABLED:
            raise CommandError("Push notifications are not enabled.")
        try:
            notes = release_notes_for_deployment(options["notes_file"])
        except ReleaseNotesError as error:
            raise CommandError(str(error)) from error
        announcement, sent = announce_release(release_id=release_id, notes=notes)
        if not sent:
            self.stdout.write(f"Release {release_id} was already announced.")
            return
        self.stdout.write(
            "Release {release_id} announced to {attempted} subscription(s); "
            "{successful} delivery attempt(s) succeeded.".format(
                release_id=announcement.release_id,
                attempted=announcement.attempted_subscription_count,
                successful=announcement.successful_delivery_count,
            )
        )
