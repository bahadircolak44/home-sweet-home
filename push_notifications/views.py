import json
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import PushSubscription
from .services import send_push_notification

MAX_REQUEST_BYTES = 8_192
MAX_ENDPOINT_LENGTH = 2_048
MAX_P256DH_LENGTH = 512
MAX_AUTH_LENGTH = 256
MAX_USER_AGENT_LENGTH = 500


def _error(message, status=400):
    return JsonResponse({"success": False, "message": message}, status=status)


def _notifications_enabled():
    return settings.PUSH_NOTIFICATIONS_ENABLED


def _request_json(request):
    if len(request.body) > MAX_REQUEST_BYTES:
        raise ValueError("The notification request is too large.")
    if not request.content_type.startswith("application/json"):
        raise ValueError("Expected a JSON request.")
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid JSON request.") from error
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data


def _valid_endpoint(value):
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or len(value) > MAX_ENDPOINT_LENGTH
    ):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.hostname:
        return None
    return value


def _subscription_data(data):
    endpoint = _valid_endpoint(data.get("endpoint"))
    keys = data.get("keys")
    if not endpoint or not isinstance(keys, dict):
        raise ValueError("A valid HTTPS subscription is required.")
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if (
        not isinstance(p256dh, str)
        or not p256dh
        or len(p256dh) > MAX_P256DH_LENGTH
        or not isinstance(auth, str)
        or not auth
        or len(auth) > MAX_AUTH_LENGTH
    ):
        raise ValueError("The subscription keys are invalid.")
    return endpoint, p256dh, auth


def _endpoint_data(data):
    endpoint = _valid_endpoint(data.get("endpoint"))
    if not endpoint:
        raise ValueError("A valid HTTPS subscription is required.")
    return endpoint


@login_required
@require_POST
def subscribe(request):
    if not _notifications_enabled():
        return _error("Notifications are not enabled.", status=404)
    try:
        endpoint, p256dh, auth = _subscription_data(_request_json(request))
    except ValueError as error:
        return _error(str(error))

    now = timezone.now()
    defaults = {
        "user": request.user,
        "p256dh": p256dh,
        "auth": auth,
        "user_agent": request.headers.get("User-Agent", "")[:MAX_USER_AGENT_LENGTH],
        "last_seen_at": now,
    }
    try:
        with transaction.atomic():
            subscription, created = PushSubscription.objects.update_or_create(
                endpoint=endpoint,
                defaults=defaults,
            )
    except IntegrityError:
        # A concurrent browser refresh may have created the endpoint first.
        with transaction.atomic():
            subscription = PushSubscription.objects.select_for_update().get(
                endpoint=endpoint
            )
            for field, value in defaults.items():
                setattr(subscription, field, value)
            subscription.save()
        created = False

    return JsonResponse({"success": True, "created": created})


@login_required
@require_POST
def unsubscribe(request):
    if not _notifications_enabled():
        return _error("Notifications are not enabled.", status=404)
    try:
        endpoint = _endpoint_data(_request_json(request))
    except ValueError as error:
        return _error(str(error))

    PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({"success": True})


@login_required
@require_POST
def test_notification(request):
    if not _notifications_enabled():
        return _error("Notifications are not enabled.", status=404)
    try:
        endpoint = _endpoint_data(_request_json(request))
    except ValueError as error:
        return _error(str(error))

    subscription = PushSubscription.objects.filter(
        user=request.user, endpoint=endpoint
    ).first()
    if subscription is None:
        return _error("No notification subscription was found for this device.", status=404)

    sent = send_push_notification(
        subscription,
        {
            "title": "Home Sweet Home",
            "body": "Notifications are working on this device.",
            "url": "/",
            "tag": "home-sweet-home-test",
        },
    )
    if not sent:
        return _error("The test notification could not be sent. Please try again.", status=502)
    return JsonResponse({"success": True, "message": "Test notification sent."})
