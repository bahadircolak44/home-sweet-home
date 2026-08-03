import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from pywebpush import WebPushException, webpush

from .models import PushSubscription, ReleaseAnnouncement

logger = logging.getLogger(__name__)

PUSH_TTL_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 5
NOTIFICATION_COOLDOWN = timedelta(minutes=10)


@dataclass(frozen=True)
class PushDeliveryResult:
    attempted: int = 0
    successful: int = 0


def _push_status_code(error):
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def remove_expired_subscription(subscription_id):
    """Remove a subscription that the push provider says is no longer valid."""
    PushSubscription.objects.filter(pk=subscription_id).delete()


def _record_activity_and_claim_notification(subscription_id):
    """Record activity and claim a notification after a genuine quiet period."""
    activity_at = timezone.now()
    inactive_before = activity_at - NOTIFICATION_COOLDOWN
    with transaction.atomic():
        subscription = (
            PushSubscription.objects.select_for_update()
            .filter(pk=subscription_id)
            .first()
        )
        if subscription is None:
            return False
        was_inactive = (
            subscription.last_activity_at is None
            or subscription.last_activity_at <= inactive_before
        )
        subscription.last_activity_at = activity_at
        update_fields = ["last_activity_at"]
        if was_inactive:
            subscription.last_notified_at = activity_at
            update_fields.append("last_notified_at")
        subscription.save(update_fields=update_fields)
    return was_inactive


def send_push_notification(subscription, payload):
    """Send one notification and isolate all provider errors from callers."""
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        return False

    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=str(settings.VAPID_PRIVATE_KEY_PATH),
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=PUSH_TTL_SECONDS,
            timeout=PUSH_TIMEOUT_SECONDS,
        )
    except WebPushException as error:
        status_code = _push_status_code(error)
        if status_code in {404, 410}:
            remove_expired_subscription(subscription.pk)
            logger.info("Removed expired push subscription id=%s.", subscription.pk)
        else:
            logger.warning(
                "Push delivery failed for subscription id=%s (HTTP status=%s).",
                subscription.pk,
                status_code or "unknown",
            )
        return False
    except Exception:
        logger.warning("Push delivery failed for subscription id=%s.", subscription.pk)
        return False
    return True


def send_to_household_members(*, household_id, actor_user_id, payload):
    """Deliver a payload to every other current member's active device."""
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        return

    subscriptions = (
        PushSubscription.objects.filter(
            user__household_memberships__household_id=household_id
        )
        .exclude(user_id=actor_user_id)
        .select_related("user")
        .distinct()
    )
    for subscription in subscriptions:
        if not _record_activity_and_claim_notification(subscription.pk):
            continue
        send_push_notification(subscription, payload)


def send_scheduled_reminder_to_household(*, household_id, payload):
    """Deliver a scheduled reminder to every current household device.

    Scheduled reminders deliberately do not use activity cooldown tracking and include
    the device belonging to the person who created the topic.
    """
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        return PushDeliveryResult()

    safe_payload = {
        "title": str(payload.get("title", "Talk Later"))[:120],
        "body": str(payload.get("body", ""))[:300],
        "url": str(payload.get("url", "/"))[:500],
        "tag": str(payload.get("tag", ""))[:120],
    }
    subscriptions = (
        PushSubscription.objects.filter(
            user__household_memberships__household_id=household_id
        )
        .select_related("user")
        .distinct()
    )
    attempted = successful = 0
    for subscription in subscriptions:
        attempted += 1
        try:
            if send_push_notification(subscription, safe_payload):
                successful += 1
        except Exception:
            # Keep a single unexpected device failure from blocking other devices.
            logger.warning(
                "Scheduled push delivery failed for subscription id=%s.", subscription.pk
            )
    return PushDeliveryResult(attempted=attempted, successful=successful)


def announce_release(*, release_id, notes):
    """Push one version announcement to each subscribed device, once per release."""
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        raise ValueError("Push notifications are not enabled.")

    with transaction.atomic():
        announcement, created = ReleaseAnnouncement.objects.select_for_update().get_or_create(
            release_id=release_id,
            defaults={"notes": "\n".join(notes)},
        )
        if not created and announcement.announced_at is not None:
            return announcement, False
        if not created:
            announcement.notes = "\n".join(notes)

        subscriptions = list(PushSubscription.objects.order_by("pk"))
        announcement.announced_at = timezone.now()
        announcement.attempted_subscription_count = len(subscriptions)
        announcement.successful_delivery_count = 0
        announcement.save(
            update_fields=[
                "notes",
                "announced_at",
                "attempted_subscription_count",
                "successful_delivery_count",
            ]
        )

    body = "What's new: " + "; ".join(notes)
    payload = {
        "title": "Home Sweet Home has a new version",
        "body": body[:300],
        "url": "/",
        "tag": f"home-sweet-home-release-{release_id[:80]}",
    }
    successful = sum(send_push_notification(subscription, payload) for subscription in subscriptions)
    ReleaseAnnouncement.objects.filter(pk=announcement.pk).update(
        successful_delivery_count=successful
    )
    announcement.successful_delivery_count = successful
    return announcement, True


def schedule_household_notification(*, household_id, actor_user_id, payload):
    """Schedule delivery after the surrounding grocery transaction commits."""
    if not settings.PUSH_NOTIFICATIONS_ENABLED:
        return

    safe_payload = {
        "title": str(payload.get("title", "Home Sweet Home"))[:120],
        "body": str(payload.get("body", ""))[:300],
        "url": str(payload.get("url", "/"))[:500],
        "tag": str(payload.get("tag", ""))[:120],
    }
    transaction.on_commit(
        partial(
            send_to_household_members,
            household_id=household_id,
            actor_user_id=actor_user_id,
            payload=safe_payload,
        )
    )
