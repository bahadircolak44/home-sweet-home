import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from households.models import Household, HouseholdMembership
from push_notifications.models import PushSubscription

from .models import DiscussionTopic
from .services import process_due_reminders, toggle_topic, update_topic


@override_settings(
    PUSH_NOTIFICATIONS_ENABLED=True,
    VAPID_PRIVATE_KEY_PATH="/tmp/test-vapid-private-key.pem",
    VAPID_SUBJECT="mailto:test@example.com",
    TALK_LATER_REMINDER_JOB_TOKEN="test-reminder-token",
)
class TalkLaterTests(TestCase):
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
        cls.home = Household.objects.create(name="Home")
        cls.other_home = Household.objects.create(name="Other home")
        HouseholdMembership.objects.create(household=cls.home, user=cls.alex)
        HouseholdMembership.objects.create(household=cls.home, user=cls.sam)
        HouseholdMembership.objects.create(household=cls.other_home, user=cls.outsider)

    def create_topic(self, **overrides):
        defaults = {
            "household": self.home,
            "title": "Discuss the holiday budget",
            "created_by": self.alex,
        }
        defaults.update(overrides)
        return DiscussionTopic.objects.create(**defaults)

    def create_subscription(self, user, endpoint):
        return PushSubscription.objects.create(
            user=user,
            endpoint=endpoint,
            p256dh="public-key",
            auth="auth-key",
            last_seen_at=timezone.now(),
        )

    def test_unauthenticated_user_is_redirected_to_login(self):
        response = self.client.get(reverse("talk_later:topic_index"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('talk_later:topic_index')}",
        )

    def test_household_members_can_access_the_same_topic(self):
        topic = self.create_topic()
        self.client.force_login(self.sam)

        response = self.client.get(reverse("talk_later:topic_detail", args=[topic.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, topic.title)

    def test_cross_household_topic_access_is_denied(self):
        topic = self.create_topic()
        self.client.force_login(self.outsider)

        for url in (
            reverse("talk_later:topic_detail", args=[topic.pk]),
            reverse("talk_later:topic_edit", args=[topic.pk]),
            reverse("talk_later:topic_delete", args=[topic.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_topic_can_be_created_without_a_schedule(self):
        self.client.force_login(self.alex)

        response = self.client.post(
            reverse("talk_later:topic_index"),
            {"title": "Choose the new dining table", "notes": "Measure first"},
        )

        topic = DiscussionTopic.objects.get(title="Choose the new dining table")
        self.assertRedirects(
            response, reverse("talk_later:topic_detail", args=[topic.pk])
        )
        self.assertIsNone(topic.scheduled_for)
        self.assertEqual(topic.notes, "Measure first")

    def test_whitespace_title_and_clearly_past_new_schedule_are_rejected(self):
        self.client.force_login(self.alex)
        past = timezone.localtime(timezone.now() - timedelta(minutes=3)).strftime(
            "%Y-%m-%dT%H:%M"
        )

        response = self.client.post(
            reverse("talk_later:topic_index"),
            {"title": "   ", "scheduled_for": past},
        )

        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "This field is required.", status_code=422)
        self.assertContains(
            response,
            "Choose a future date and time, or leave the reminder empty.",
            status_code=422,
        )
        self.assertFalse(DiscussionTopic.objects.exists())

    def test_notes_are_limited_to_two_thousand_characters(self):
        self.client.force_login(self.alex)

        response = self.client.post(
            reverse("talk_later:topic_index"),
            {"title": "Plan next weekend", "notes": "x" * 2001},
        )

        self.assertEqual(response.status_code, 422)
        self.assertContains(
            response,
            "Ensure this value has at most 2000 characters",
            status_code=422,
        )
        self.assertFalse(DiscussionTopic.objects.exists())

    def test_toggle_sets_completion_metadata_and_done_topics_are_not_processed(self):
        topic = self.create_topic(scheduled_for=timezone.now() - timedelta(minutes=1))

        toggle_topic(topic=topic, user=self.sam)
        topic.refresh_from_db()
        counts = process_due_reminders()

        self.assertTrue(topic.is_done)
        self.assertEqual(topic.completed_by, self.sam)
        self.assertIsNotNone(topic.completed_at)
        self.assertEqual(counts["claimed"], 0)
        self.assertIsNone(topic.reminder_processed_at)

    def test_reopening_preserves_processed_reminder_state(self):
        topic = self.create_topic(
            is_done=True,
            completed_by=self.alex,
            completed_at=timezone.now(),
            scheduled_for=timezone.now() - timedelta(minutes=1),
            reminder_processed_at=timezone.now(),
            reminder_sent_at=timezone.now(),
        )

        toggle_topic(topic=topic, user=self.sam)
        topic.refresh_from_db()

        self.assertFalse(topic.is_done)
        self.assertIsNone(topic.completed_by)
        self.assertIsNone(topic.completed_at)
        self.assertIsNotNone(topic.reminder_processed_at)
        self.assertIsNotNone(topic.reminder_sent_at)

    def test_rescheduling_clears_reminder_state(self):
        topic = self.create_topic(
            scheduled_for=timezone.now() + timedelta(hours=1),
            reminder_claimed_at=timezone.now(),
            reminder_processed_at=timezone.now(),
            reminder_sent_at=timezone.now(),
        )

        changed = update_topic(
            topic=topic,
            title=topic.title,
            notes="Updated notes",
            scheduled_for=timezone.now() + timedelta(hours=2),
            user=self.sam,
        )

        self.assertIsNone(changed.reminder_claimed_at)
        self.assertIsNone(changed.reminder_processed_at)
        self.assertIsNone(changed.reminder_sent_at)

    @patch("push_notifications.services.webpush")
    def test_due_processing_ignores_ineligible_topics_and_does_not_duplicate(self, webpush):
        due = self.create_topic(scheduled_for=timezone.now() - timedelta(minutes=1))
        self.create_topic(title="Future", scheduled_for=timezone.now() + timedelta(hours=1))
        self.create_topic(title="Unscheduled")
        self.create_topic(
            title="Done",
            scheduled_for=timezone.now() - timedelta(minutes=1),
            is_done=True,
            completed_by=self.alex,
            completed_at=timezone.now(),
        )
        self.create_topic(
            title="Processed",
            scheduled_for=timezone.now() - timedelta(minutes=1),
            reminder_processed_at=timezone.now(),
        )
        self.create_subscription(self.alex, "https://push.example.test/alex-due")

        first_counts = process_due_reminders()
        second_counts = process_due_reminders()
        due.refresh_from_db()

        self.assertEqual(first_counts["claimed"], 1)
        self.assertEqual(first_counts["processed"], 1)
        self.assertEqual(second_counts["claimed"], 0)
        self.assertEqual(webpush.call_count, 1)
        self.assertIsNotNone(due.reminder_processed_at)
        self.assertIsNotNone(due.reminder_sent_at)

    @patch("push_notifications.services.webpush")
    def test_stale_claims_can_retry(self, webpush):
        topic = self.create_topic(
            scheduled_for=timezone.now() - timedelta(minutes=1),
            reminder_claimed_at=timezone.now() - timedelta(minutes=11),
        )
        self.create_subscription(self.alex, "https://push.example.test/stale-claim")

        counts = process_due_reminders()
        topic.refresh_from_db()

        self.assertEqual(counts["claimed"], 1)
        self.assertEqual(webpush.call_count, 1)
        self.assertIsNotNone(topic.reminder_processed_at)

    @patch("push_notifications.services.webpush")
    def test_reminder_goes_to_every_current_household_device_including_creator(self, webpush):
        topic = self.create_topic(
            title="Call the vet together",
            notes="Do not show this in the notification.",
            scheduled_for=timezone.now() - timedelta(minutes=1),
        )
        creator_device = self.create_subscription(
            self.alex, "https://push.example.test/alex-reminder"
        )
        member_device = self.create_subscription(
            self.sam, "https://push.example.test/sam-reminder"
        )
        self.create_subscription(self.outsider, "https://push.example.test/outsider-reminder")

        counts = process_due_reminders()
        delivered_endpoints = {
            call.kwargs["subscription_info"]["endpoint"] for call in webpush.call_args_list
        }
        payload = json.loads(webpush.call_args_list[0].kwargs["data"])

        self.assertEqual(counts["sent"], 1)
        self.assertEqual(webpush.call_count, 2)
        self.assertEqual(delivered_endpoints, {creator_device.endpoint, member_device.endpoint})
        self.assertEqual(payload["title"], "Talk Later")
        self.assertEqual(payload["body"], "It's time to discuss: Call the vet together")
        self.assertEqual(payload["url"], reverse("talk_later:topic_detail", args=[topic.pk]))
        self.assertNotIn("Do not show", payload["body"])

    def test_no_subscription_topics_are_processed_once(self):
        topic = self.create_topic(scheduled_for=timezone.now() - timedelta(minutes=1))

        counts = process_due_reminders()
        topic.refresh_from_db()

        self.assertEqual(counts["no_subscription"], 1)
        self.assertIsNotNone(topic.reminder_processed_at)
        self.assertIsNone(topic.reminder_sent_at)

    @patch("push_notifications.services.webpush")
    def test_push_failure_does_not_crash_the_batch(self, webpush):
        from pywebpush import WebPushException

        topic = self.create_topic(scheduled_for=timezone.now() - timedelta(minutes=1))
        self.create_subscription(self.alex, "https://push.example.test/failing-reminder")
        webpush.side_effect = WebPushException("provider failure")

        counts = process_due_reminders()
        topic.refresh_from_db()

        self.assertEqual(counts["failed"], 1)
        self.assertIsNotNone(topic.reminder_processed_at)
        self.assertIsNone(topic.reminder_sent_at)

    def test_scheduler_token_is_required_and_valid_requests_return_counts(self):
        denied = self.client.post(reverse("talk_later_process_reminders"))
        accepted = self.client.post(
            reverse("talk_later_process_reminders"),
            HTTP_X_REMINDER_TOKEN="test-reminder-token",
        )

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(
            set(accepted.json()),
            {"claimed", "processed", "sent", "no_subscription", "failed"},
        )

    def test_dashboard_summary_shows_pending_count_and_next_reminder(self):
        next_time = timezone.now() + timedelta(hours=2)
        self.create_topic(scheduled_for=next_time)
        self.create_topic(title="Unscheduled")
        self.client.force_login(self.alex)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "2</strong> pending topics")
        self.assertContains(response, "Talk Later")
