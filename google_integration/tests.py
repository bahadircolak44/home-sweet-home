import base64
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from httplib2 import Response

from households.models import Household, HouseholdMembership
from talk_later.models import DiscussionTopic
from talk_later.services import InvalidDiscussionOperation, create_topic, delete_topic, toggle_topic

from .crypto import decrypt_refresh_token, encrypt_refresh_token
from .models import GoogleAccountConnection
from .oauth import (
    GoogleAccountLinkError,
    GoogleIdentity,
    GoogleTokenResult,
    link_google_identity,
)
from .services import sync_topic_calendar_event

TEST_FERNET_KEY = base64.urlsafe_b64encode(b"0" * 32).decode()
GOOGLE_SETTINGS = {
    "GOOGLE_OAUTH_ENABLED": True,
    "GOOGLE_CALENDAR_ENABLED": True,
    "GOOGLE_OAUTH_CLIENT_ID": "test-google-client-id",
    "GOOGLE_OAUTH_CLIENT_SECRET": "test-google-client-secret",
    "GOOGLE_OAUTH_REDIRECT_URI": "https://home.example.test/accounts/google/callback/",
    "GOOGLE_ALLOWED_EMAILS": ("alex@example.com", "sam@example.com"),
    "GOOGLE_LEGACY_USER_MAP": {
        "alex@example.com": "alex",
        "sam@example.com": "sam",
    },
    "GOOGLE_TOKEN_ENCRYPTION_KEY": TEST_FERNET_KEY,
    "GOOGLE_CALENDAR_EVENT_DURATION_MINUTES": 30,
    "PASSWORD_LOGIN_ENABLED": True,
}


@override_settings(**GOOGLE_SETTINGS)
class GoogleIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.alex = user_model.objects.create_user(
            username="alex", password="test-password", first_name="Alex"
        )
        cls.sam = user_model.objects.create_user(
            username="sam", password="test-password", first_name="Sam"
        )
        cls.outsider = user_model.objects.create_user(
            username="outsider", password="test-password", first_name="Outsider"
        )
        cls.household = Household.objects.create(name="Home")
        cls.other_household = Household.objects.create(name="Other")
        HouseholdMembership.objects.create(household=cls.household, user=cls.alex)
        HouseholdMembership.objects.create(household=cls.household, user=cls.sam)
        HouseholdMembership.objects.create(
            household=cls.other_household, user=cls.outsider
        )

    def identity(self, **overrides):
        values = {
            "subject": "google-alex-subject",
            "email": "alex@example.com",
            "email_verified": True,
            "given_name": "Alex",
            "family_name": "Example",
        }
        values.update(overrides)
        return GoogleIdentity(**values)

    def token_result(self, **overrides):
        values = {
            "refresh_token": "refresh-token-alex",
            "id_token": "unused-in-direct-link-tests",
            "granted_scopes": [
                "openid",
                "email",
                "profile",
                "https://www.googleapis.com/auth/calendar.events.owned",
            ],
        }
        values.update(overrides)
        return GoogleTokenResult(**values)

    def create_connection(self, user, email, subject):
        return GoogleAccountConnection.objects.create(
            user=user,
            google_subject=subject,
            email=email,
            email_verified=True,
            encrypted_refresh_token=encrypt_refresh_token(f"refresh-token-{user.username}"),
            granted_scopes=self.token_result().granted_scopes,
        )

    def topic(self, **overrides):
        values = {
            "household": self.household,
            "title": "Discuss the holiday budget",
            "created_by": self.alex,
            "scheduled_for": timezone.now() + timedelta(days=1),
            "calendar_sync_status": DiscussionTopic.CalendarSyncStatus.PENDING,
        }
        values.update(overrides)
        return DiscussionTopic.objects.create(**values)

    def mock_calendar_service(self):
        service = MagicMock()
        service.events.return_value.insert.return_value.execute.return_value = {
            "id": "calendar-event-id",
            "htmlLink": "https://calendar.google.test/event",
        }
        service.events.return_value.patch.return_value.execute.return_value = {
            "id": "calendar-event-id",
            "htmlLink": "https://calendar.google.test/event",
        }
        return service

    def test_oauth_start_stores_state_and_safe_next_url(self):
        response = self.client.get(
            reverse("google_integration:start"),
            {"next": reverse("talk_later:topic_index")},
        )

        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["include_granted_scopes"], ["true"])
        self.assertIn("calendar.events.owned", query["scope"][0])
        self.assertEqual(self.client.session["google_oauth_state"], query["state"][0])
        self.assertEqual(
            self.client.session["google_oauth_next"], reverse("talk_later:topic_index")
        )

    def test_oauth_start_discards_external_next_url(self):
        self.client.get(reverse("google_integration:start"), {"next": "https://evil.test"})

        self.assertEqual(self.client.session["google_oauth_next"], "")

    def test_invalid_oauth_state_is_rejected(self):
        self.client.get(reverse("google_integration:start"))

        response = self.client.get(
            reverse("google_integration:callback"), {"state": "wrong", "code": "code"}
        )

        self.assertRedirects(response, reverse("login"))
        self.assertFalse(GoogleAccountConnection.objects.exists())

    def test_unverified_and_non_allowlisted_accounts_are_rejected(self):
        with self.assertRaises(GoogleAccountLinkError):
            link_google_identity(
                identity=self.identity(email_verified=False), token_result=self.token_result()
            )
        with self.assertRaises(GoogleAccountLinkError):
            link_google_identity(
                identity=self.identity(email="not-approved@example.com"),
                token_result=self.token_result(),
            )
        self.assertFalse(GoogleAccountConnection.objects.exists())

    def test_mapped_existing_user_is_linked_without_losing_data(self):
        permission = Permission.objects.get(codename="view_user")
        self.alex.user_permissions.add(permission)
        topic = self.topic()
        original_id = self.alex.pk

        connection, created, _new_token = link_google_identity(
            identity=self.identity(), token_result=self.token_result()
        )

        self.alex.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(connection.user_id, original_id)
        self.assertEqual(self.alex.pk, original_id)
        self.assertTrue(self.alex.household_memberships.filter(household=self.household).exists())
        self.assertTrue(self.alex.user_permissions.filter(pk=permission.pk).exists())
        self.assertEqual(topic.created_by_id, original_id)
        self.assertEqual(self.alex.email, "alex@example.com")

    def test_unknown_google_user_is_never_created(self):
        original_count = get_user_model().objects.count()

        with self.assertRaises(GoogleAccountLinkError):
            link_google_identity(
                identity=self.identity(
                    subject="unknown-subject", email="unknown@example.com"
                ),
                token_result=self.token_result(),
            )

        self.assertEqual(get_user_model().objects.count(), original_count)

    def test_refresh_token_is_encrypted_and_preserved_when_google_omits_it(self):
        connection, _created, _new_token = link_google_identity(
            identity=self.identity(), token_result=self.token_result()
        )
        encrypted_token = connection.encrypted_refresh_token

        connection, _created, new_token = link_google_identity(
            identity=self.identity(),
            token_result=self.token_result(refresh_token=""),
        )

        self.assertFalse(new_token)
        self.assertNotEqual(encrypted_token, "refresh-token-alex")
        self.assertEqual(decrypt_refresh_token(encrypted_token), "refresh-token-alex")
        self.assertEqual(connection.encrypted_refresh_token, encrypted_token)

    @patch("google_integration.views.verify_id_token")
    @patch("google_integration.views.exchange_authorization_code")
    def test_google_login_creates_a_normal_django_session(self, exchange, verify):
        exchange.return_value = self.token_result()
        verify.return_value = self.identity()
        self.client.get(reverse("google_integration:start"))
        state = self.client.session["google_oauth_state"]

        response = self.client.get(
            reverse("google_integration:callback"), {"state": state, "code": "test-code"}
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.alex.pk)

    def test_password_login_still_works_when_enabled(self):
        response = self.client.post(
            reverse("login"), {"username": "alex", "password": "test-password"}
        )

        self.assertRedirects(response, reverse("home"))

    @patch("google_integration.services.build_calendar_service")
    def test_scheduled_topic_inserts_one_organizer_event_and_invites_only_household(self, build_service):
        self.create_connection(self.alex, "alex@example.com", "google-alex-subject")
        self.create_connection(self.sam, "sam@example.com", "google-sam-subject")
        self.create_connection(
            self.outsider, "outsider@example.com", "google-outsider-subject"
        )
        topic = self.topic()
        service = self.mock_calendar_service()
        build_service.return_value = service

        sync_topic_calendar_event(topic)

        insert_kwargs = service.events.return_value.insert.call_args.kwargs
        body = insert_kwargs["body"]
        self.assertEqual(insert_kwargs["calendarId"], "primary")
        self.assertEqual(insert_kwargs["sendUpdates"], "all")
        self.assertEqual(body["attendees"], [{"email": "sam@example.com"}])
        self.assertEqual(body["reminders"], {"useDefault": False})
        self.assertFalse(body["guestsCanModify"])
        self.assertFalse(body["guestsCanInviteOthers"])
        self.assertTrue(body["guestsCanSeeOtherGuests"])
        self.assertEqual(service.events.return_value.patch.call_count, 0)
        topic.refresh_from_db()
        self.assertEqual(topic.google_calendar_event_id, "calendar-event-id")
        self.assertEqual(topic.calendar_sync_status, topic.CalendarSyncStatus.SYNCED)

    @patch("google_integration.services.build_calendar_service")
    def test_editing_patches_the_same_event_and_preserves_rsvp(self, build_service):
        self.create_connection(self.alex, "alex@example.com", "google-alex-subject")
        self.create_connection(self.sam, "sam@example.com", "google-sam-subject")
        topic = self.topic(google_calendar_event_id="existing-event")
        service = self.mock_calendar_service()
        service.events.return_value.get.return_value.execute.return_value = {
            "attendees": [{"email": "sam@example.com", "responseStatus": "accepted"}]
        }
        build_service.return_value = service

        sync_topic_calendar_event(topic)

        patch_kwargs = service.events.return_value.patch.call_args.kwargs
        self.assertEqual(patch_kwargs["eventId"], "existing-event")
        self.assertEqual(patch_kwargs["sendUpdates"], "all")
        self.assertEqual(
            patch_kwargs["body"]["attendees"],
            [{"email": "sam@example.com", "responseStatus": "accepted"}],
        )
        self.assertEqual(service.events.return_value.insert.call_count, 0)

    @patch("google_integration.services.build_calendar_service")
    def test_removing_a_schedule_deletes_the_event(self, build_service):
        self.create_connection(self.alex, "alex@example.com", "google-alex-subject")
        topic = self.topic(scheduled_for=None, google_calendar_event_id="existing-event")
        service = self.mock_calendar_service()
        build_service.return_value = service

        sync_topic_calendar_event(topic)

        delete_kwargs = service.events.return_value.delete.call_args.kwargs
        self.assertEqual(delete_kwargs["eventId"], "existing-event")
        self.assertEqual(delete_kwargs["sendUpdates"], "all")
        topic.refresh_from_db()
        self.assertEqual(topic.google_calendar_event_id, "")
        self.assertEqual(topic.calendar_sync_status, topic.CalendarSyncStatus.NOT_SCHEDULED)

    @patch("google_integration.services.build_calendar_service")
    def test_topic_deletion_is_blocked_when_calendar_deletion_fails(self, build_service):
        self.create_connection(self.alex, "alex@example.com", "google-alex-subject")
        topic = self.topic(google_calendar_event_id="existing-event")
        build_service.side_effect = RuntimeError("temporary provider failure")

        with self.assertRaises(InvalidDiscussionOperation):
            delete_topic(topic=topic, user=self.alex)

        self.assertTrue(DiscussionTopic.objects.filter(pk=topic.pk).exists())

    @patch("google_integration.services.build_calendar_service")
    def test_event_not_found_allows_local_deletion(self, build_service):
        self.create_connection(self.alex, "alex@example.com", "google-alex-subject")
        topic = self.topic(google_calendar_event_id="missing-event")
        service = self.mock_calendar_service()
        service.events.return_value.delete.return_value.execute.side_effect = HttpError(
            Response({"status": "404"}), b"missing"
        )
        build_service.return_value = service

        delete_topic(topic=topic, user=self.alex)

        self.assertFalse(DiscussionTopic.objects.filter(pk=topic.pk).exists())

    @patch("google_integration.services.build_calendar_service")
    def test_calendar_failure_does_not_roll_back_local_topic_creation(self, build_service):
        self.create_connection(self.alex, "alex@example.com", "google-alex-subject")
        build_service.side_effect = RuntimeError("temporary provider failure")

        with self.captureOnCommitCallbacks(execute=True):
            topic = create_topic(
                household=self.household,
                title="Plan next weekend",
                notes="",
                scheduled_for=timezone.now() + timedelta(days=1),
                user=self.alex,
            )

        topic.refresh_from_db()
        self.assertTrue(DiscussionTopic.objects.filter(pk=topic.pk).exists())
        self.assertEqual(topic.calendar_sync_status, topic.CalendarSyncStatus.FAILED)

    @patch("google_integration.services.build_calendar_service")
    def test_revoked_credentials_require_reauthorization(self, build_service):
        connection = self.create_connection(
            self.alex, "alex@example.com", "google-alex-subject"
        )
        topic = self.topic()
        build_service.side_effect = RefreshError("revoked")

        sync_topic_calendar_event(topic)

        topic.refresh_from_db()
        connection.refresh_from_db()
        self.assertEqual(
            topic.calendar_sync_status, topic.CalendarSyncStatus.REAUTHORIZATION_REQUIRED
        )
        self.assertTrue(connection.reauthorization_required)

    @patch("google_integration.services.build_calendar_service")
    def test_marking_done_does_not_modify_calendar_event(self, build_service):
        self.create_connection(self.alex, "alex@example.com", "google-alex-subject")
        topic = self.topic(google_calendar_event_id="existing-event")

        toggle_topic(topic=topic, user=self.sam)

        build_service.assert_not_called()
        topic.refresh_from_db()
        self.assertTrue(topic.is_done)
        self.assertEqual(topic.google_calendar_event_id, "existing-event")

    @patch("talk_later.views.sync_topic_calendar_event")
    def test_calendar_retry_is_household_authorized(self, sync):
        topic = self.topic()
        self.client.force_login(self.outsider)
        denied = self.client.post(
            reverse("talk_later:topic_calendar_retry", args=[topic.pk])
        )
        self.assertEqual(denied.status_code, 404)

        self.client.force_login(self.sam)
        accepted = self.client.post(
            reverse("talk_later:topic_calendar_retry", args=[topic.pk])
        )
        self.assertRedirects(accepted, reverse("talk_later:topic_detail", args=[topic.pk]))
        sync.assert_called_once()
