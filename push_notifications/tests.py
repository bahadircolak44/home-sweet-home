import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from households.models import Household, HouseholdMembership
from shopping.models import ShoppingList
from shopping.services import add_item, complete_list

from .models import PushSubscription
from .services import send_push_notification


@override_settings(
    PUSH_NOTIFICATIONS_ENABLED=True,
    VAPID_PRIVATE_KEY_PATH="/tmp/test-vapid-private-key.pem",
    VAPID_SUBJECT="mailto:test@example.com",
)
class PushNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.alex = user_model.objects.create_user("alex", password="password")
        cls.sam = user_model.objects.create_user("sam", password="password")
        cls.outsider = user_model.objects.create_user("outsider", password="password")
        cls.home = Household.objects.create(name="Home")
        cls.other_home = Household.objects.create(name="Other home")
        HouseholdMembership.objects.create(household=cls.home, user=cls.alex)
        HouseholdMembership.objects.create(household=cls.home, user=cls.sam)
        HouseholdMembership.objects.create(household=cls.other_home, user=cls.outsider)
        cls.shopping_list = ShoppingList.objects.create(
            household=cls.home,
            name="Albert",
            icon="albert-heijn",
            list_type=ShoppingList.ListType.ALBERT,
            created_by=cls.alex,
        )
        cls.legacy_list = ShoppingList.objects.create(
            household=cls.home, name="Weekly groceries", created_by=cls.alex
        )

    def subscription_payload(self, endpoint="https://push.example.test/subscription"):
        return {
            "endpoint": endpoint,
            "keys": {"p256dh": "public-key", "auth": "auth-key"},
        }

    def post_json(self, url, payload):
        return self.client.post(url, payload, content_type="application/json")

    def create_subscription(self, user, endpoint):
        return PushSubscription.objects.create(
            user=user,
            endpoint=endpoint,
            p256dh="public-key",
            auth="auth-key",
            last_seen_at=timezone.now(),
        )

    def test_subscription_creation_belongs_to_authenticated_user(self):
        self.client.force_login(self.alex)

        response = self.post_json(
            reverse("push_notifications:subscribe"), self.subscription_payload()
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PushSubscription.objects.get().user, self.alex)
        self.assertNotContains(response, "public-key")

    def test_resubscribing_endpoint_updates_ownership_without_duplicates(self):
        endpoint = "https://push.example.test/shared"
        self.create_subscription(self.alex, endpoint)
        self.client.force_login(self.sam)

        response = self.post_json(
            reverse("push_notifications:subscribe"),
            self.subscription_payload(endpoint),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 1)
        self.assertEqual(PushSubscription.objects.get().user, self.sam)

    def test_user_cannot_unsubscribe_another_users_endpoint(self):
        endpoint = "https://push.example.test/alex"
        self.create_subscription(self.alex, endpoint)
        self.client.force_login(self.sam)

        response = self.post_json(reverse("push_notifications:unsubscribe"), {"endpoint": endpoint})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PushSubscription.objects.filter(endpoint=endpoint).exists())

    @patch("push_notifications.services.webpush")
    def test_recipients_are_limited_to_other_household_members(self, webpush):
        actor_subscription = self.create_subscription(
            self.alex, "https://push.example.test/alex"
        )
        recipient_subscription = self.create_subscription(
            self.sam, "https://push.example.test/sam"
        )
        outsider_subscription = self.create_subscription(
            self.outsider, "https://push.example.test/outsider"
        )
        del actor_subscription, outsider_subscription

        with self.captureOnCommitCallbacks(execute=True):
            add_item(
                shopping_list=self.shopping_list,
                text="Milk",
                quantity=2,
                description="Private notes must not be sent.",
                user=self.alex,
            )

        self.assertEqual(webpush.call_count, 1)
        subscription_info = webpush.call_args.kwargs["subscription_info"]
        self.assertEqual(subscription_info["endpoint"], recipient_subscription.endpoint)
        payload = webpush.call_args.kwargs["data"]
        self.assertIn("2\\u00d7 Milk", payload)
        self.assertNotIn("Private notes", payload)

    @patch("push_notifications.services.webpush")
    def test_shopping_notification_is_sent_only_after_commit(self, webpush):
        self.create_subscription(self.sam, "https://push.example.test/sam")

        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                add_item(
                    shopping_list=self.shopping_list,
                    text="Milk",
                    quantity=1,
                    description="",
                    user=self.alex,
                )
                self.assertFalse(webpush.called)

        self.assertTrue(webpush.called)

    @patch("push_notifications.services.webpush")
    def test_stale_push_response_removes_subscription(self, webpush):
        from pywebpush import WebPushException

        for status_code in (404, 410):
            with self.subTest(status_code=status_code):
                subscription = self.create_subscription(
                    self.sam, f"https://push.example.test/stale-{status_code}"
                )
                webpush.side_effect = WebPushException(
                    "gone", response=Mock(status_code=status_code)
                )

                sent = send_push_notification(subscription, {"title": "Home Sweet Home"})

                self.assertFalse(sent)
                self.assertFalse(PushSubscription.objects.filter(pk=subscription.pk).exists())

    @patch("push_notifications.services.webpush")
    def test_push_failure_does_not_fail_grocery_operation(self, webpush):
        self.create_subscription(self.sam, "https://push.example.test/sam-failure")
        from pywebpush import WebPushException

        webpush.side_effect = WebPushException("provider failure")

        with self.captureOnCommitCallbacks(execute=True):
            item = add_item(
                shopping_list=self.shopping_list,
                text="Bread",
                quantity=1,
                description="",
                user=self.alex,
            )

        self.assertEqual(item.text, "Bread")

    @patch("push_notifications.views.send_push_notification")
    def test_test_notification_cannot_target_another_users_subscription(self, send):
        endpoint = "https://push.example.test/alex-test"
        self.create_subscription(self.alex, endpoint)
        self.client.force_login(self.sam)

        response = self.post_json(reverse("push_notifications:test"), {"endpoint": endpoint})

        self.assertEqual(response.status_code, 404)
        send.assert_not_called()

    @patch("push_notifications.services.webpush")
    def test_completed_list_payload_is_safe(self, webpush):
        self.create_subscription(self.sam, "https://push.example.test/complete")

        with self.captureOnCommitCallbacks(execute=True):
            complete_list(shopping_list=self.legacy_list, user=self.alex)

        payload = json.loads(webpush.call_args.kwargs["data"])
        self.assertEqual(payload["body"], "alex completed Weekly groceries.")
        self.assertNotIn(str(self.legacy_list.pk), payload["body"])

    @patch("push_notifications.services.webpush")
    def test_device_receives_a_new_notification_only_after_ten_minutes_of_inactivity(
        self, webpush
    ):
        subscription = self.create_subscription(
            self.sam, "https://push.example.test/activity-window"
        )

        with self.captureOnCommitCallbacks(execute=True):
            add_item(
                shopping_list=self.shopping_list,
                text="Milk",
                quantity=1,
                description="",
                user=self.alex,
            )
        subscription.refresh_from_db()
        self.assertIsNotNone(subscription.last_notified_at)
        first_activity_at = subscription.last_activity_at

        with self.captureOnCommitCallbacks(execute=True):
            add_item(
                shopping_list=self.shopping_list,
                text="Bread",
                quantity=1,
                description="",
                user=self.alex,
            )
        self.assertEqual(webpush.call_count, 1)
        subscription.refresh_from_db()
        self.assertGreater(subscription.last_activity_at, first_activity_at)

        PushSubscription.objects.filter(pk=subscription.pk).update(
            last_notified_at=timezone.now() - timedelta(minutes=10, seconds=1)
        )
        with self.captureOnCommitCallbacks(execute=True):
            add_item(
                shopping_list=self.shopping_list,
                text="Butter",
                quantity=1,
                description="",
                user=self.alex,
            )
        self.assertEqual(webpush.call_count, 1)

        PushSubscription.objects.filter(pk=subscription.pk).update(
            last_activity_at=timezone.now() - timedelta(minutes=10, seconds=1)
        )
        with self.captureOnCommitCallbacks(execute=True):
            add_item(
                shopping_list=self.shopping_list,
                text="Eggs",
                quantity=1,
                description="",
                user=self.alex,
            )
        self.assertEqual(webpush.call_count, 2)
