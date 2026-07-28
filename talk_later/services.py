import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from households.services import get_household_for_user
from push_notifications.services import send_scheduled_reminder_to_household

from .models import DiscussionTopic

logger = logging.getLogger(__name__)

REMINDER_CLAIM_TIMEOUT = timedelta(minutes=10)
DEFAULT_REMINDER_BATCH_LIMIT = 100


class InvalidDiscussionOperation(Exception):
    pass


@dataclass(frozen=True)
class ReminderProcessingCounts:
    claimed: int = 0
    processed: int = 0
    sent: int = 0
    no_subscription: int = 0
    failed: int = 0

    def as_dict(self):
        return {
            "claimed": self.claimed,
            "processed": self.processed,
            "sent": self.sent,
            "no_subscription": self.no_subscription,
            "failed": self.failed,
        }


def topics_for_user(user):
    household = get_household_for_user(user)
    if household is None:
        return DiscussionTopic.objects.none()
    return (
        DiscussionTopic.objects.available_to(user)
        .filter(household=household)
        .select_related("household", "created_by", "completed_by")
    )


def upcoming_topics_for_user(user):
    return (
        topics_for_user(user)
        .filter(is_done=False)
        .order_by(models.F("scheduled_for").asc(nulls_last=True), "-updated_at")
    )


def completed_topics_for_user(user):
    return topics_for_user(user).filter(is_done=True).order_by("-completed_at")


def talk_later_summary_for_user(user):
    pending_topics = topics_for_user(user).filter(is_done=False)
    return pending_topics.aggregate(
        pending_topic_count=models.Count("id"),
        next_scheduled_for=models.Min("scheduled_for"),
    )


@transaction.atomic
def create_topic(*, household, title, notes, scheduled_for, user):
    calendar_sync_status = DiscussionTopic.CalendarSyncStatus.NOT_SCHEDULED
    if scheduled_for is not None and settings.GOOGLE_CALENDAR_ENABLED:
        calendar_sync_status = DiscussionTopic.CalendarSyncStatus.PENDING
    topic = DiscussionTopic.objects.create(
        household=household,
        title=title,
        notes=notes,
        scheduled_for=scheduled_for,
        created_by=user,
        calendar_sync_status=calendar_sync_status,
    )
    if scheduled_for is not None and settings.GOOGLE_CALENDAR_ENABLED:
        from google_integration.services import queue_topic_calendar_sync

        queue_topic_calendar_sync(topic.pk)
    return topic


@transaction.atomic
def update_topic(*, topic, title, notes, scheduled_for, user):
    locked_topic = DiscussionTopic.objects.select_for_update().get(pk=topic.pk)
    schedule_changed = locked_topic.scheduled_for != scheduled_for
    calendar_fields_changed = (
        locked_topic.title != title
        or locked_topic.notes != notes
        or schedule_changed
    )
    locked_topic.title = title
    locked_topic.notes = notes
    locked_topic.scheduled_for = scheduled_for
    update_fields = ["title", "notes", "scheduled_for", "updated_at"]
    if schedule_changed:
        locked_topic.reminder_claimed_at = None
        locked_topic.reminder_processed_at = None
        locked_topic.reminder_sent_at = None
        update_fields.extend(
            [
                "reminder_claimed_at",
                "reminder_processed_at",
                "reminder_sent_at",
            ]
        )
    should_sync_calendar = (
        settings.GOOGLE_CALENDAR_ENABLED
        and calendar_fields_changed
        and (locked_topic.scheduled_for is not None or locked_topic.google_calendar_event_id)
    )
    if should_sync_calendar:
        locked_topic.calendar_sync_status = DiscussionTopic.CalendarSyncStatus.PENDING
        locked_topic.calendar_sync_error = ""
        update_fields.extend(["calendar_sync_status", "calendar_sync_error"])
    locked_topic.save(update_fields=update_fields)
    if should_sync_calendar:
        from google_integration.services import queue_topic_calendar_sync

        queue_topic_calendar_sync(locked_topic.pk)
    return locked_topic


@transaction.atomic
def toggle_topic(*, topic, user):
    locked_topic = DiscussionTopic.objects.select_for_update().get(pk=topic.pk)
    if locked_topic.is_done:
        locked_topic.is_done = False
        locked_topic.completed_by = None
        locked_topic.completed_at = None
    else:
        locked_topic.is_done = True
        locked_topic.completed_by = user
        locked_topic.completed_at = timezone.now()
    locked_topic.save(
        update_fields=["is_done", "completed_by", "completed_at", "updated_at"]
    )
    return locked_topic


@transaction.atomic
def delete_topic(*, topic, user):
    topic_to_delete = DiscussionTopic.objects.get(pk=topic.pk)
    if topic_to_delete.google_calendar_event_id:
        from google_integration.services import CalendarSyncError, delete_topic_calendar_event

        try:
            delete_topic_calendar_event(topic_to_delete, raise_on_error=True)
        except CalendarSyncError as error:
            raise InvalidDiscussionOperation(str(error)) from error
    with transaction.atomic():
        locked_topic = DiscussionTopic.objects.select_for_update().get(pk=topic.pk)
        locked_topic.delete()


def _eligible_due_topics(*, now):
    stale_before = now - REMINDER_CLAIM_TIMEOUT
    return (
        DiscussionTopic.objects.filter(
            is_done=False,
            scheduled_for__isnull=False,
            scheduled_for__lte=now,
            reminder_processed_at__isnull=True,
        )
        .filter(
            models.Q(reminder_claimed_at__isnull=True)
            | models.Q(reminder_claimed_at__lte=stale_before)
        )
        .order_by("scheduled_for", "pk")
    )


def claim_due_topics(*, limit=DEFAULT_REMINDER_BATCH_LIMIT, now=None):
    """Claim a bounded set of due topics without holding locks during delivery."""
    now = now or timezone.now()
    limit = max(1, min(int(limit), DEFAULT_REMINDER_BATCH_LIMIT))
    with transaction.atomic():
        topics = list(
            _eligible_due_topics(now=now)
            .select_for_update(skip_locked=True)
            .select_related("household")[:limit]
        )
        for topic in topics:
            topic.reminder_claimed_at = now
            topic.save(update_fields=["reminder_claimed_at", "updated_at"])
    return topics


def _mark_reminder_processed(*, topic, claim_time, delivered_count):
    """Finalize only the unchanged schedule this worker claimed."""
    now = timezone.now()
    with transaction.atomic():
        current_topic = (
            DiscussionTopic.objects.select_for_update()
            .filter(pk=topic.pk, reminder_claimed_at=claim_time)
            .first()
        )
        if current_topic is None:
            return False
        current_topic.reminder_processed_at = now
        if delivered_count:
            current_topic.reminder_sent_at = now
        current_topic.save(
            update_fields=[
                "reminder_processed_at",
                "reminder_sent_at",
                "updated_at",
            ]
        )
    return True


def process_due_reminders(*, limit=DEFAULT_REMINDER_BATCH_LIMIT):
    """Deliver due reminders once, with short database transactions around claims."""
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        logger.info("Talk Later reminder processing skipped because push is disabled.")
        return ReminderProcessingCounts().as_dict()

    topics = claim_due_topics(limit=limit)
    processed = sent = no_subscription = failed = 0
    for topic in topics:
        attempted = successful = 0
        try:
            result = send_scheduled_reminder_to_household(
                household_id=topic.household_id,
                payload={
                    "title": "Talk Later",
                    "body": f"It's time to discuss: {topic.title}",
                    "url": reverse("talk_later:topic_detail", args=[topic.pk]),
                    "tag": f"talk-later-{topic.pk}",
                },
            )
            attempted = result.attempted
            successful = result.successful
        except Exception:
            logger.warning("Talk Later reminder delivery failed for topic id=%s.", topic.pk)

        if not _mark_reminder_processed(
            topic=topic,
            claim_time=topic.reminder_claimed_at,
            delivered_count=successful,
        ):
            continue

        processed += 1
        if successful:
            sent += 1
        elif not attempted:
            no_subscription += 1
        else:
            failed += 1

    return ReminderProcessingCounts(
        claimed=len(topics),
        processed=processed,
        sent=sent,
        no_subscription=no_subscription,
        failed=failed,
    ).as_dict()
