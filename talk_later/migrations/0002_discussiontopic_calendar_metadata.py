from django.db import migrations, models
from django.utils import timezone


def set_initial_calendar_statuses(apps, schema_editor):
    DiscussionTopic = apps.get_model("talk_later", "DiscussionTopic")
    DiscussionTopic.objects.filter(scheduled_for__isnull=True).update(
        calendar_sync_status="NOT_SCHEDULED"
    )
    DiscussionTopic.objects.filter(
        scheduled_for__gt=timezone.now(), is_done=False
    ).update(calendar_sync_status="PENDING")


class Migration(migrations.Migration):
    dependencies = [("talk_later", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="discussiontopic",
            name="calendar_last_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="discussiontopic",
            name="calendar_sync_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="discussiontopic",
            name="calendar_sync_status",
            field=models.CharField(
                choices=[
                    ("NOT_SCHEDULED", "Not scheduled"),
                    ("PENDING", "Pending"),
                    ("SYNCED", "Synced"),
                    ("FAILED", "Failed"),
                    ("REAUTHORIZATION_REQUIRED", "Reconnect required"),
                ],
                default="NOT_SCHEDULED",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="discussiontopic",
            name="calendar_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="discussiontopic",
            name="google_calendar_event_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="discussiontopic",
            name="google_calendar_html_link",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="discussiontopic",
            name="google_calendar_id",
            field=models.CharField(default="primary", max_length=100),
        ),
        migrations.AddIndex(
            model_name="discussiontopic",
            index=models.Index(
                fields=["calendar_sync_status", "scheduled_for"],
                name="talk_later_calendar_idx",
            ),
        ),
        migrations.RunPython(set_initial_calendar_statuses, migrations.RunPython.noop),
    ]
