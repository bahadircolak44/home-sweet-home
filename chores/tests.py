import json
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from households.models import Household, HouseholdMembership
from push_notifications.models import PushSubscription

from .models import ChoreSession, ChoreTask, ChoreTemplate
from .services import complete_session, create_task


class ChoreFlowTests(TestCase):
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
        cls.other_home = Household.objects.create(name="Other Home")
        HouseholdMembership.objects.create(household=cls.home, user=cls.alex)
        HouseholdMembership.objects.create(household=cls.home, user=cls.sam)
        HouseholdMembership.objects.create(household=cls.other_home, user=cls.outsider)

    def setUp(self):
        self.session = ChoreSession.objects.create(
            household=self.home,
            name="This Week",
            notes="Shared tasks",
            created_by=self.alex,
        )

    def test_unauthenticated_user_is_redirected_to_login(self):
        response = self.client.get(reverse("chores:session_index"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('chores:session_index')}",
        )

    def test_household_members_can_access_the_same_session(self):
        self.client.force_login(self.sam)

        response = self.client.get(
            reverse("chores:session_detail", args=[self.session.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This Week")

    def test_cross_household_session_task_and_template_access_is_denied(self):
        task = ChoreTask.objects.create(
            session=self.session, title="Clean the kitchen", created_by=self.alex
        )
        template = ChoreTemplate.objects.create(
            household=self.home, title="Take out the bins", created_by=self.alex
        )
        self.client.force_login(self.outsider)

        for url in (
            reverse("chores:session_detail", args=[self.session.pk]),
            reverse("chores:task_edit", args=[task.pk]),
            reverse("chores:template_edit", args=[template.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_assignee_must_belong_to_the_session_household(self):
        self.client.force_login(self.alex)

        response = self.client.post(
            reverse("chores:task_add", args=[self.session.pk]),
            {
                "title": "Clean the kitchen",
                "assignee": self.outsider.pk,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(ChoreTask.objects.exists())

    def test_custom_task_can_be_created_and_assigned(self):
        self.client.force_login(self.alex)

        response = self.client.post(
            reverse("chores:task_add", args=[self.session.pk]),
            {
                "title": "Clean the kitchen",
                "due_date": "2026-08-12",
                "assignee": self.sam.pk,
            },
        )

        self.assertRedirects(
            response, reverse("chores:session_detail", args=[self.session.pk])
        )
        task = ChoreTask.objects.get(title="Clean the kitchen")
        self.assertEqual(task.assignee, self.sam)
        self.assertEqual(task.quantity, 1)
        self.assertEqual(task.due_date, date(2026, 8, 12))
        detail = self.client.get(reverse("chores:session_detail", args=[self.session.pk]))
        self.assertContains(detail, "Sam")
        self.assertContains(detail, "Clean the kitchen")

    def test_quick_template_can_be_added_multiple_times_to_a_session(self):
        self.client.force_login(self.alex)
        template_response = self.client.post(
            reverse("chores:template_create"),
            {"title": "Take out the bins", "default_assignee": self.sam.pk},
        )
        self.assertRedirects(template_response, reverse("chores:quick_list"))
        template = ChoreTemplate.objects.get(title="Take out the bins")
        quick_list = self.client.get(reverse("chores:quick_list"))
        self.assertContains(quick_list, "Default assignee: Sam")
        quick_add_url = reverse(
            "chores:task_quick_add", args=[self.session.pk, template.pk]
        )

        first_response = self.client.post(quick_add_url, HTTP_HX_REQUEST="true")
        second_response = self.client.post(quick_add_url, HTTP_HX_REQUEST="true")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(
            ChoreTask.objects.filter(
                session=self.session, source_template=template
            ).count(),
            2,
        )

    def test_toggling_task_sets_and_clears_completion_metadata(self):
        task = ChoreTask.objects.create(
            session=self.session, title="Water the plants", created_by=self.alex
        )
        self.client.force_login(self.sam)
        toggle_url = reverse("chores:task_toggle", args=[task.pk])

        self.client.post(toggle_url)
        task.refresh_from_db()
        self.assertTrue(task.is_done)
        self.assertEqual(task.completed_by, self.sam)
        self.assertIsNotNone(task.completed_at)

        self.client.post(toggle_url)
        task.refresh_from_db()
        self.assertFalse(task.is_done)
        self.assertIsNone(task.completed_by)
        self.assertIsNone(task.completed_at)

    def test_task_changes_touch_the_parent_session(self):
        initial_update = self.session.updated_at
        self.client.force_login(self.alex)

        self.client.post(
            reverse("chores:task_add", args=[self.session.pk]),
            {"title": "Vacuum the living room", "assignee": ""},
        )

        self.session.refresh_from_db()
        self.assertGreater(self.session.updated_at, initial_update)

    def test_completed_sessions_are_read_only(self):
        task = ChoreTask.objects.create(
            session=self.session, title="Clean the bathroom", created_by=self.alex
        )
        self.client.force_login(self.alex)
        self.client.post(reverse("chores:session_complete", args=[self.session.pk]))
        self.session.refresh_from_db()

        self.assertEqual(self.session.status, ChoreSession.Status.COMPLETED)
        self.assertEqual(
            self.client.post(
                reverse("chores:task_add", args=[self.session.pk]),
                {"title": "Crafted task", "assignee": ""},
            ).status_code,
            404,
        )
        toggle_response = self.client.post(reverse("chores:task_toggle", args=[task.pk]))
        self.assertRedirects(
            toggle_response,
            reverse("chores:history_detail", args=[self.session.pk]),
        )
        task.refresh_from_db()
        self.assertFalse(task.is_done)

    def test_active_and_completed_sessions_appear_on_the_correct_pages(self):
        completed = ChoreSession.objects.create(
            household=self.home, name="Weekend", created_by=self.alex
        )
        complete_session(session=completed, user=self.alex)
        self.client.force_login(self.alex)

        active = self.client.get(reverse("chores:session_index"))
        history = self.client.get(reverse("chores:history"))

        self.assertContains(active, "This Week")
        self.assertNotContains(active, "Weekend")
        self.assertContains(history, "Weekend")
        self.assertNotContains(history, "This Week")

    def test_dashboard_summary_counts_active_sessions_and_remaining_tasks(self):
        done_task = ChoreTask.objects.create(
            session=self.session, title="Done task", created_by=self.alex
        )
        ChoreTask.objects.create(
            session=self.session, title="Remaining task", created_by=self.alex
        )
        done_task.is_done = True
        done_task.completed_by = self.alex
        done_task.completed_at = timezone.now()
        done_task.save(
            update_fields=["is_done", "completed_by", "completed_at", "updated_at"]
        )
        self.client.force_login(self.alex)

        dashboard = self.client.get(reverse("home"))

        self.assertContains(dashboard, "1</strong> active session")
        self.assertContains(dashboard, "1</strong> task remaining")

    def test_completed_tasks_with_same_title_can_be_adjusted(self):
        ChoreTask.objects.create(
            session=self.session,
            title="Clean the kitchen",
            is_done=True,
            created_by=self.alex,
            completed_by=self.alex,
            completed_at=timezone.now(),
        )
        ChoreTask.objects.create(
            session=self.session,
            title="Clean the kitchen",
            is_done=True,
            created_by=self.alex,
            completed_by=self.sam,
            completed_at=timezone.now(),
        )
        self.client.force_login(self.alex)

        response = self.client.post(
            reverse("chores:completed_task_add", args=[self.session.pk]),
            {"title": "Clean the kitchen"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3×")
        self.assertContains(response, "Completed by Alex, Sam")
        self.assertEqual(
            ChoreTask.objects.filter(
                session=self.session, title="Clean the kitchen", is_done=True
            ).count(),
            3,
        )

        response = self.client.post(
            reverse("chores:completed_task_remove", args=[self.session.pk]),
            {"title": "Clean the kitchen"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2×")
        self.assertEqual(
            ChoreTask.objects.filter(
                session=self.session, title="Clean the kitchen", is_done=True
            ).count(),
            2,
        )

    def test_completed_tasks_are_grouped_at_the_bottom_with_assignee_names(self):
        ChoreTask.objects.create(
            session=self.session,
            title="Still needed task",
            assignee=self.alex,
            created_by=self.alex,
        )
        alex_done = ChoreTask.objects.create(
            session=self.session,
            title="Alex completed task",
            quantity=2,
            assignee=self.alex,
            is_done=True,
            completed_by=self.alex,
            completed_at=timezone.now(),
            created_by=self.alex,
        )
        sam_done = ChoreTask.objects.create(
            session=self.session,
            title="Sam completed task",
            assignee=self.sam,
            is_done=True,
            completed_by=self.sam,
            completed_at=timezone.now(),
            created_by=self.alex,
        )
        del alex_done, sam_done
        self.client.force_login(self.alex)

        response = self.client.get(
            reverse("chores:session_detail", args=[self.session.pk])
        )

        self.assertContains(response, "Still needed")
        self.assertContains(response, "Completed")
        self.assertContains(response, "Completed by Alex")
        self.assertContains(response, "Completed by Sam")
        self.assertLess(
            response.content.index(b'id="tasks-title"'),
            response.content.index(b'id="completed-tasks-title"'),
        )

    def test_quick_add_collapses_templates_after_the_first_three(self):
        for number in range(4):
            ChoreTemplate.objects.create(
                household=self.home,
                title=f"Reusable chore {number}",
                created_by=self.alex,
            )
        self.client.force_login(self.alex)

        response = self.client.get(
            reverse("chores:session_detail", args=[self.session.pk])
        )

        self.assertContains(response, "Show more chores")
        self.assertContains(response, 'class="chore-quick-add__more"')

    @override_settings(
        PUSH_NOTIFICATIONS_ENABLED=True,
        VAPID_PRIVATE_KEY_PATH="/tmp/test-vapid-private-key.pem",
        VAPID_SUBJECT="mailto:test@example.com",
    )
    @patch("push_notifications.services.webpush")
    def test_chore_notifications_exclude_the_actor(self, webpush):
        PushSubscription.objects.create(
            user=self.alex,
            endpoint="https://push.example.test/alex-chores",
            p256dh="public-key",
            auth="auth-key",
            last_seen_at=timezone.now(),
        )
        recipient_subscription = PushSubscription.objects.create(
            user=self.sam,
            endpoint="https://push.example.test/sam-chores",
            p256dh="public-key",
            auth="auth-key",
            last_seen_at=timezone.now(),
        )

        with self.captureOnCommitCallbacks(execute=True):
            create_task(
                session=self.session,
                title="Clean the kitchen",
                assignee=self.sam,
                user=self.alex,
            )

        self.assertEqual(webpush.call_count, 1)
        self.assertEqual(
            webpush.call_args.kwargs["subscription_info"]["endpoint"],
            recipient_subscription.endpoint,
        )
        payload = json.loads(webpush.call_args.kwargs["data"])
        self.assertEqual(payload["body"], "Alex assigned Clean the kitchen to Sam.")
