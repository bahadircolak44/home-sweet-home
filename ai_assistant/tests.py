import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from chores.models import ChoreSession, ChoreTask
from households.models import Household, HouseholdMembership
from shopping.models import ShoppingItem, ShoppingList
from talk_later.models import DiscussionTopic

from .models import AssistantCommand
from .openai_client import ResponseShapeError, ToolCall, transcribe_audio


@override_settings(
    AI_ASSISTANT_ENABLED=True,
    OPENAI_API_KEY="test-key-not-used",
    OPENAI_COMMAND_MODEL="test-command-model",
    OPENAI_TRANSCRIPTION_MODEL="test-transcription-model",
    AI_COMMANDS_PER_MINUTE=10,
)
class AiAssistantTests(TestCase):
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

    def setUp(self):
        self.shopping_list = ShoppingList.objects.create(
            household=self.home,
            name="Albert",
            icon="albert-heijn",
            list_type=ShoppingList.ListType.ALBERT,
            created_by=self.alex,
        )
        self.session = ChoreSession.objects.create(
            household=self.home, name="Weekend Cleaning", created_by=self.alex
        )
        self.other_list = ShoppingList.objects.create(
            household=self.other_home,
            name="Other list",
            icon="🛒",
            created_by=self.outsider,
        )
        self.client.force_login(self.alex)

    def command_url(self):
        return reverse("ai_assistant:text_command")

    def call_text(self, tool_call, command="Add milk to Albert", request_id=None):
        with patch("ai_assistant.services.interpret_command", return_value=tool_call):
            return self.client.post(
                self.command_url(),
                {"command": command, "request_id": str(request_id or uuid.uuid4())},
            )

    def grocery_call(self, list_id=None, item="Milk", quantity=1):
        return ToolCall(
            "propose_add_grocery_item",
            {
                "shopping_list_id": list_id or self.shopping_list.pk,
                "item_name": item,
                "quantity": quantity,
                "description": "",
            },
        )

    def needs_confirmation(self, tool_call=None):
        response = self.call_text(tool_call or self.grocery_call())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "needs_confirmation")
        return AssistantCommand.objects.get()

    def test_unauthenticated_text_and_audio_requests_redirect_to_login(self):
        self.client.logout()
        text = self.client.post(self.command_url(), {"command": "Add milk"})
        audio = self.client.post(reverse("ai_assistant:audio_command"), {})

        self.assertEqual(text.status_code, 302)
        self.assertEqual(audio.status_code, 302)

    def test_user_without_a_household_cannot_use_the_assistant(self):
        user = get_user_model().objects.create_user(
            username="no-household", password="test-password"
        )
        self.client.force_login(user)

        response = self.client.post(
            self.command_url(), {"command": "Add milk", "request_id": str(uuid.uuid4())}
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AssistantCommand.objects.exists())

    @override_settings(AI_ASSISTANT_ENABLED=False)
    def test_dashboard_panel_is_hidden_when_disabled(self):
        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "Quick Add with AI")

    def test_text_interpretation_creates_only_a_proposal(self):
        response = self.call_text(self.grocery_call(item="Milk", quantity=2))

        command = AssistantCommand.objects.get()
        self.assertEqual(response.json()["status"], "needs_confirmation")
        self.assertEqual(command.status, AssistantCommand.Status.NEEDS_CONFIRMATION)
        self.assertEqual(command.action_type, AssistantCommand.ActionType.ADD_GROCERY_ITEM)
        self.assertFalse(ShoppingItem.objects.exists())

    def test_turkish_transcript_is_accepted(self):
        response = self.call_text(
            self.grocery_call(item="elma", quantity=2),
            command="Albert listesine iki tane elma ekle.",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AssistantCommand.objects.get().transcript, "Albert listesine iki tane elma ekle.")

    def test_audio_transcription_is_used_without_storing_audio(self):
        audio = SimpleUploadedFile("command.webm", b"voice", content_type="audio/webm")
        call = self.grocery_call(item="Bread")
        with patch("ai_assistant.services.transcribe_audio", return_value="Add bread to Albert") as transcribe:
            with patch("ai_assistant.services.interpret_command", return_value=call):
                response = self.client.post(
                    reverse("ai_assistant:audio_command"),
                    {"audio": audio, "request_id": str(uuid.uuid4())},
                )

        command = AssistantCommand.objects.get()
        self.assertEqual(response.json()["status"], "needs_confirmation")
        self.assertEqual(command.source, AssistantCommand.Source.AUDIO)
        self.assertEqual(command.transcript, "Add bread to Albert")
        self.assertFalse(hasattr(command, "audio"))
        transcribe.assert_called_once()

    @patch("ai_assistant.openai_client._client")
    def test_transcription_adapts_django_upload_to_an_sdk_file_tuple(self, client):
        client.return_value.audio.transcriptions.create.return_value = {"text": "Add milk"}
        audio = SimpleUploadedFile(
            "command.webm", b"voice-data", content_type="audio/webm"
        )

        transcript = transcribe_audio(audio=audio)

        self.assertEqual(transcript, "Add milk")
        client.return_value.audio.transcriptions.create.assert_called_once_with(
            model="test-transcription-model",
            file=("command.webm", b"voice-data", "audio/webm"),
        )

    def test_grocery_confirmation_uses_existing_service_and_is_idempotent(self):
        command = self.needs_confirmation(self.grocery_call(item="Milk", quantity=3))
        url = reverse("ai_assistant:confirm", args=[command.pk])

        first = self.client.post(url)
        second = self.client.post(url)

        self.assertEqual(first.json()["status"], "executed")
        self.assertEqual(second.json()["status"], "executed")
        self.assertEqual(ShoppingItem.objects.filter(text="Milk").count(), 1)
        self.assertEqual(ShoppingItem.objects.get(text="Milk").quantity, 3)

    def test_chore_confirmation_validates_assignee_and_creates_task(self):
        call = ToolCall(
            "propose_add_chore_task",
            {
                "chore_session_id": self.session.pk,
                "task_title": "Clean the kitchen",
                "assignee_user_id": self.sam.pk,
            },
        )
        command = self.needs_confirmation(call)

        response = self.client.post(reverse("ai_assistant:confirm", args=[command.pk]))

        self.assertEqual(response.json()["status"], "executed")
        task = ChoreTask.objects.get(title="Clean the kitchen")
        self.assertEqual(task.assignee, self.sam)

    def test_talk_later_confirmation_creates_scheduled_topic_through_service(self):
        scheduled_for = (timezone.now() + timedelta(hours=2)).isoformat()
        call = ToolCall(
            "propose_add_talk_later_topic",
            {"title": "Discuss holiday budget", "notes": "", "scheduled_for": scheduled_for},
        )
        command = self.needs_confirmation(call)

        response = self.client.post(reverse("ai_assistant:confirm", args=[command.pk]))

        self.assertEqual(response.json()["status"], "executed")
        self.assertIsNotNone(DiscussionTopic.objects.get().scheduled_for)

    def test_another_user_cannot_confirm_a_command(self):
        command = self.needs_confirmation()
        self.client.force_login(self.sam)

        response = self.client.post(reverse("ai_assistant:confirm", args=[command.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ShoppingItem.objects.exists())

    def test_cross_household_and_hallucinated_ids_are_rejected(self):
        for list_id in (self.other_list.pk, 999999):
            with self.subTest(list_id=list_id):
                response = self.call_text(self.grocery_call(list_id=list_id))
                self.assertEqual(response.status_code, 502)
                self.assertFalse(ShoppingItem.objects.exists())
                AssistantCommand.objects.all().delete()

    def test_completed_list_is_rejected_at_confirmation(self):
        command = self.needs_confirmation()
        self.shopping_list.status = ShoppingList.Status.COMPLETED
        self.shopping_list.completed_by = self.alex
        self.shopping_list.completed_at = timezone.now()
        self.shopping_list.save()

        response = self.client.post(reverse("ai_assistant:confirm", args=[command.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertFalse(ShoppingItem.objects.exists())

    def test_expired_and_cancelled_proposals_do_not_execute(self):
        expired = self.needs_confirmation()
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])
        expired_response = self.client.post(reverse("ai_assistant:confirm", args=[expired.pk]))

        AssistantCommand.objects.all().delete()
        cancelled = self.needs_confirmation()
        self.client.post(reverse("ai_assistant:cancel", args=[cancelled.pk]))
        cancelled_response = self.client.post(reverse("ai_assistant:confirm", args=[cancelled.pk]))

        self.assertEqual(expired_response.status_code, 409)
        self.assertEqual(cancelled_response.status_code, 409)
        self.assertFalse(ShoppingItem.objects.exists())

    def test_unresolved_and_multiple_action_commands_create_no_domain_data(self):
        call = ToolCall(
            "report_unresolved_command",
            {
                "reason": "multiple_actions",
                "target_type": "action",
                "requested_name": "",
                "clarification_question": "",
            },
        )
        response = self.call_text(call, command="Add milk and bread")

        self.assertEqual(response.json()["status"], "unresolved")
        self.assertFalse(ShoppingItem.objects.exists())
        self.assertFalse(ChoreTask.objects.exists())
        self.assertFalse(DiscussionTopic.objects.exists())

    def test_invalid_model_response_creates_no_domain_data(self):
        with patch(
            "ai_assistant.services.interpret_command",
            side_effect=ResponseShapeError("multiple calls"),
        ):
            response = self.client.post(
                self.command_url(),
                {"command": "Add milk", "request_id": str(uuid.uuid4())},
            )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(ShoppingItem.objects.exists())

    def test_audio_size_and_type_are_rejected_before_openai(self):
        bad_type = SimpleUploadedFile("command.txt", b"voice", content_type="text/plain")
        with patch("ai_assistant.services.transcribe_audio") as transcribe:
            response = self.client.post(
                reverse("ai_assistant:audio_command"),
                {"audio": bad_type, "request_id": str(uuid.uuid4())},
            )

        self.assertEqual(response.status_code, 400)
        transcribe.assert_not_called()

    @override_settings(AI_COMMANDS_PER_MINUTE=1)
    def test_rate_limiting_returns_429(self):
        self.call_text(self.grocery_call())

        response = self.call_text(self.grocery_call(item="Bread"))

        self.assertEqual(response.status_code, 429)

    def test_context_only_contains_authorized_active_household_data(self):
        completed = ShoppingList.objects.create(
            household=self.home, name="Completed", icon="🛒", created_by=self.alex
        )
        completed.status = ShoppingList.Status.COMPLETED
        completed.completed_by = self.alex
        completed.completed_at = timezone.now()
        completed.save()
        call = self.grocery_call()
        with patch("ai_assistant.services.interpret_command", return_value=call) as interpret:
            self.client.post(
                self.command_url(),
                {"command": "Add milk", "request_id": str(uuid.uuid4())},
            )

        context = interpret.call_args.kwargs["context"]
        self.assertEqual(
            context["active_grocery_lists"],
            [
                {"id": self.shopping_list.pk, "name": "Albert"},
                {
                    "id": ShoppingList.objects.get(
                        household=self.home,
                        list_type=ShoppingList.ListType.TURKISH_MARKET,
                    ).pk,
                    "name": "Türk Market",
                },
            ],
        )
        self.assertNotIn("email", context["household_members"][0])
        self.assertEqual(context["active_chore_sessions"], [{"id": self.session.pk, "name": "Weekend Cleaning"}])
