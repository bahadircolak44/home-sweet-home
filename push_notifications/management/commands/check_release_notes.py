from django.core.management.base import BaseCommand, CommandError

from push_notifications.release_notes import ReleaseNotesError, release_notes_for_deployment


class Command(BaseCommand):
    help = "Validate the user-facing notes required before deployment."

    def add_arguments(self, parser):
        parser.add_argument("--notes-file", default="RELEASE_NOTES.md")

    def handle(self, *args, **options):
        try:
            notes = release_notes_for_deployment(options["notes_file"])
        except ReleaseNotesError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(f"Release notes ready ({len(notes)} item(s)).")
