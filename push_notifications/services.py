import json
import logging
from functools import partial

from django.conf import settings
from django.db import transaction

from pywebpush import WebPushException, webpush

from .models import PushSubscription

logger = logging.getLogger(__name__)

PUSH_TTL_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 5


def _push_status_code(error):
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def remove_expired_subscription(subscription_id):
    """Remove a subscription that the push provider says is no longer valid."""
    PushSubscription.objects.filter(pk=subscription_id).delete()


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
        send_push_notification(subscription, payload)


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
