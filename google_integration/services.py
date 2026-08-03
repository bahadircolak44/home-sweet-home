from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from households.models import HouseholdMembership
from talk_later.models import DiscussionTopic

from .crypto import TokenEncryptionError, decrypt_refresh_token
from .models import GoogleAccountConnection
from .oauth import GOOGLE_TOKEN_URL, REQUIRED_SCOPES


class CalendarSyncError(Exception):
    pass


REAUTHORIZATION_MESSAGE = "Reconnect Google Calendar to continue syncing."
CALENDAR_FAILURE_MESSAGE = "Google Calendar could not be updated. Try again later."
CREATOR_CONNECTION_MESSAGE = "The topic creator needs to connect Google Calendar."


def build_calendar_service(connection):
    credentials = Credentials(
        token=None,
        refresh_token=decrypt_refresh_token(connection.encrypted_refresh_token),
        token_uri=GOOGLE_TOKEN_URL,
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=connection.granted_scopes or list(REQUIRED_SCOPES),
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def calendar_attendees_for_topic(topic):
    member_ids = HouseholdMembership.objects.filter(household_id=topic.household_id).exclude(
        user_id=topic.created_by_id
    ).values_list("user_id", flat=True)
    connections = GoogleAccountConnection.objects.filter(
        user_id__in=member_ids, email_verified=True
    ).values_list("email", flat=True)
    return [{"email": email} for email in sorted({email.strip().lower() for email in connections})]


def calendar_attendee_warning_for_topic(topic):
    member_count = HouseholdMembership.objects.filter(household_id=topic.household_id).exclude(
        user_id=topic.created_by_id
    ).count()
    invited_count = len(calendar_attendees_for_topic(topic))
    if member_count > invited_count:
        return "Some household members have not connected Google Calendar and were not invited."
    return ""


def _topic_url(topic):
    redirect_uri = urlsplit(settings.GOOGLE_OAUTH_REDIRECT_URI)
    return (
        f"{redirect_uri.scheme}://{redirect_uri.netloc}"
        f"{reverse('talk_later:topic_detail', args=[topic.pk])}"
    )


def _merged_attendees(topic, existing_attendees=None):
    existing_by_email = {
        attendee.get("email", "").lower(): attendee
        for attendee in (existing_attendees or [])
        if attendee.get("email")
    }
    attendees = []
    for attendee in calendar_attendees_for_topic(topic):
        previous = existing_by_email.get(attendee["email"])
        if previous:
            attendees.append(
                {
                    key: value
                    for key, value in previous.items()
                    if key
                    in {
                        "email",
                        "responseStatus",
                        "comment",
                        "additionalGuests",
                        "optional",
                    }
                }
            )
        else:
            attendees.append(attendee)
    return attendees


def build_topic_event_body(topic, *, existing_attendees=None):
    end = topic.scheduled_for + timedelta(
        minutes=settings.GOOGLE_CALENDAR_EVENT_DURATION_MINUTES
    )
    description_parts = []
    if topic.notes:
        description_parts.append(topic.notes)
    description_parts.extend(["Created by Home Sweet Home", _topic_url(topic)])
    return {
        "summary": f"Talk Later: {topic.title}",
        "description": "\n\n".join(description_parts),
        "start": {"dateTime": topic.scheduled_for.isoformat(), "timeZone": settings.TIME_ZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": settings.TIME_ZONE},
        "attendees": _merged_attendees(topic, existing_attendees),
        "guestsCanModify": False,
        "guestsCanInviteOthers": False,
        "guestsCanSeeOtherGuests": True,
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 30}],
        },
        "extendedProperties": {"private": {"home_sweet_home_topic_id": str(topic.pk)}},
    }


def _set_topic_status(topic_id, *, status, error="", event_id=None, html_link=None):
    values = {
        "calendar_sync_status": status,
        "calendar_sync_error": error[:500],
        "calendar_last_attempt_at": timezone.now(),
    }
    if status == DiscussionTopic.CalendarSyncStatus.SYNCED:
        values["calendar_synced_at"] = timezone.now()
    if event_id is not None:
        values["google_calendar_event_id"] = event_id
    if html_link is not None:
        values["google_calendar_html_link"] = html_link
    DiscussionTopic.objects.filter(pk=topic_id).update(**values)


def _mark_failure(topic, connection, *, reauthorization=False):
    message = REAUTHORIZATION_MESSAGE if reauthorization else CALENDAR_FAILURE_MESSAGE
    status = (
        DiscussionTopic.CalendarSyncStatus.REAUTHORIZATION_REQUIRED
        if reauthorization
        else DiscussionTopic.CalendarSyncStatus.FAILED
    )
    _set_topic_status(topic.pk, status=status, error=message)
    if connection is not None:
        update_values = {"last_error": message}
        if reauthorization:
            update_values["reauthorization_required"] = True
        GoogleAccountConnection.objects.filter(pk=connection.pk).update(**update_values)
    return message


def _connection_for_topic(topic):
    try:
        return topic.created_by.google_account_connection
    except GoogleAccountConnection.DoesNotExist:
        return None


def _http_status(error):
    return getattr(getattr(error, "resp", None), "status", None)


def create_topic_calendar_event(topic):
    return sync_topic_calendar_event(topic)


def update_topic_calendar_event(topic):
    return sync_topic_calendar_event(topic)


def sync_topic_calendar_event(topic):
    """Synchronize one topic without allowing a Calendar failure to undo local changes."""
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return None
    topic = DiscussionTopic.objects.select_related("created_by", "household").get(pk=topic.pk)
    if topic.scheduled_for is None:
        return delete_topic_calendar_event(topic)

    connection = _connection_for_topic(topic)
    if connection is None or not connection.has_refresh_token:
        _set_topic_status(
            topic.pk,
            status=DiscussionTopic.CalendarSyncStatus.FAILED,
            error=CREATOR_CONNECTION_MESSAGE,
        )
        return None
    if connection.reauthorization_required:
        _mark_failure(topic, connection, reauthorization=True)
        return None

    try:
        service = build_calendar_service(connection)
        if topic.google_calendar_event_id:
            existing_event = (
                service.events()
                .get(calendarId=topic.google_calendar_id, eventId=topic.google_calendar_event_id)
                .execute()
            )
            event = (
                service.events()
                .patch(
                    calendarId=topic.google_calendar_id,
                    eventId=topic.google_calendar_event_id,
                    body=build_topic_event_body(
                        topic, existing_attendees=existing_event.get("attendees", [])
                    ),
                    sendUpdates="all",
                )
                .execute()
            )
        else:
            event = (
                service.events()
                .insert(
                    calendarId=topic.google_calendar_id,
                    body=build_topic_event_body(topic),
                    sendUpdates="all",
                )
                .execute()
            )
        event_id = event.get("id", topic.google_calendar_event_id)
        if not event_id:
            raise CalendarSyncError("Google Calendar could not be updated.")
        _set_topic_status(
            topic.pk,
            status=DiscussionTopic.CalendarSyncStatus.SYNCED,
            error="",
            event_id=event_id,
            html_link=event.get("htmlLink", topic.google_calendar_html_link),
        )
        GoogleAccountConnection.objects.filter(pk=connection.pk).update(
            last_calendar_success_at=timezone.now(),
            reauthorization_required=False,
            last_error="",
        )
        return event
    except RefreshError:
        _mark_failure(topic, connection, reauthorization=True)
    except TokenEncryptionError:
        _mark_failure(topic, connection, reauthorization=True)
    except HttpError as error:
        _mark_failure(topic, connection, reauthorization=_http_status(error) == 401)
    except Exception:
        _mark_failure(topic, connection)
    return None


def delete_topic_calendar_event(topic, *, raise_on_error=False):
    """Delete the remote event and retain metadata on failure for a safe retry."""
    if not topic.google_calendar_event_id:
        _set_topic_status(
            topic.pk,
            status=DiscussionTopic.CalendarSyncStatus.NOT_SCHEDULED,
            error="",
            event_id="",
            html_link="",
        )
        return True
    if not settings.GOOGLE_CALENDAR_ENABLED:
        _set_topic_status(
            topic.pk,
            status=DiscussionTopic.CalendarSyncStatus.FAILED,
            error=CALENDAR_FAILURE_MESSAGE,
        )
        if raise_on_error:
            raise CalendarSyncError(CALENDAR_FAILURE_MESSAGE)
        return False

    topic = DiscussionTopic.objects.select_related("created_by").get(pk=topic.pk)
    connection = _connection_for_topic(topic)
    if connection is None or not connection.has_refresh_token:
        message = _mark_failure(topic, connection)
        if raise_on_error:
            raise CalendarSyncError(message)
        return False
    try:
        service = build_calendar_service(connection)
        (
            service.events()
            .delete(
                calendarId=topic.google_calendar_id,
                eventId=topic.google_calendar_event_id,
                sendUpdates="all",
            )
            .execute()
        )
    except HttpError as error:
        if _http_status(error) != 404:
            message = _mark_failure(topic, connection, reauthorization=_http_status(error) == 401)
            if raise_on_error:
                raise CalendarSyncError(message) from error
            return False
    except RefreshError as error:
        message = _mark_failure(topic, connection, reauthorization=True)
        if raise_on_error:
            raise CalendarSyncError(message) from error
        return False
    except Exception as error:
        message = _mark_failure(topic, connection)
        if raise_on_error:
            raise CalendarSyncError(message) from error
        return False

    _set_topic_status(
        topic.pk,
        status=DiscussionTopic.CalendarSyncStatus.NOT_SCHEDULED,
        error="",
        event_id="",
        html_link="",
    )
    GoogleAccountConnection.objects.filter(pk=connection.pk).update(
        last_calendar_success_at=timezone.now(), last_error=""
    )
    return True


def sync_future_topics_for_user(user, *, force=False, limit=None):
    topics = DiscussionTopic.objects.filter(
        created_by=user,
        is_done=False,
        scheduled_for__gt=timezone.now(),
    ).order_by("scheduled_for", "pk")
    if not force:
        topics = topics.exclude(
            calendar_sync_status=DiscussionTopic.CalendarSyncStatus.SYNCED
        )
    if limit is not None:
        topics = topics[:limit]
    return [sync_topic_calendar_event(topic) for topic in topics]


def sync_household_future_topics(household, *, force=False, limit=None):
    topics = DiscussionTopic.objects.filter(
        household=household,
        is_done=False,
        scheduled_for__gt=timezone.now(),
    ).order_by("scheduled_for", "pk")
    if not force:
        topics = topics.exclude(
            calendar_sync_status=DiscussionTopic.CalendarSyncStatus.SYNCED
        )
    if limit is not None:
        topics = topics[:limit]
    return [sync_topic_calendar_event(topic) for topic in topics]


def queue_topic_calendar_sync(topic_id):
    transaction.on_commit(
        lambda: sync_topic_calendar_event(DiscussionTopic.objects.get(pk=topic_id))
    )
