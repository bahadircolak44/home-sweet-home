import logging
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from chores.forms import ChoreTaskForm
from chores.services import active_sessions_for_user, create_task
from shopping.forms import ShoppingItemForm
from shopping.services import active_lists_for_user, add_items
from talk_later.forms import DiscussionTopicForm
from talk_later.services import create_topic

from .context import build_household_context, context_snapshot, display_name
from .models import AssistantCommand
from .openai_client import ProviderError, ResponseShapeError, interpret_command, transcribe_audio
from .tools import TOOL_NAMES

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_LENGTH = 1000
SUPPORTED_AUDIO_TYPES = {
    "audio/webm",
    "audio/mp4",
    "audio/m4a",
    "audio/ogg",
    "application/ogg",
    "audio/wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
}
UNRESOLVED_REASONS = {
    "unsupported_action",
    "not_an_addition",
    "multiple_actions",
    "target_not_found",
    "ambiguous_target",
    "missing_information",
    "invalid_datetime",
}
TARGET_TYPES = {
    "grocery_list",
    "chore_session",
    "household_member",
    "talk_later",
    "action",
    "unknown",
}


class AssistantValidationError(Exception):
    pass


class AssistantRateLimitError(Exception):
    pass


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _require_arguments(arguments, names):
    if set(arguments) != set(names):
        raise AssistantValidationError("The proposal has unsupported fields.")
    return [arguments[name] for name in names]


def _snapshot_ids(snapshot, name):
    values = snapshot.get(name)
    if not isinstance(values, list) or any(not _is_integer(value) for value in values):
        raise AssistantValidationError("The proposal is no longer valid.")
    return set(values)


def _validated_active_list(*, list_id, user, household, snapshot):
    if not _is_integer(list_id) or list_id not in _snapshot_ids(snapshot, "grocery_list_ids"):
        raise AssistantValidationError("That grocery list is not available.")
    shopping_list = (
        active_lists_for_user(user)
        .filter(household=household, pk=list_id)
        .first()
    )
    if shopping_list is None:
        raise AssistantValidationError("That grocery list is no longer active.")
    return shopping_list


def _validated_active_session(*, session_id, user, household, snapshot):
    if not _is_integer(session_id) or session_id not in _snapshot_ids(snapshot, "chore_session_ids"):
        raise AssistantValidationError("That chore session is not available.")
    session = (
        active_sessions_for_user(user)
        .filter(household=household, pk=session_id)
        .first()
    )
    if session is None:
        raise AssistantValidationError("That chore session is no longer active.")
    return session


def _validated_member(*, member_id, household, snapshot):
    if member_id is None:
        return None
    if not _is_integer(member_id) or member_id not in _snapshot_ids(
        snapshot, "household_member_ids"
    ):
        raise AssistantValidationError("That household member is not available.")
    member = (
        get_user_model()
        .objects.filter(pk=member_id, household_memberships__household=household)
        .distinct()
        .first()
    )
    if member is None:
        raise AssistantValidationError("That household member is not available.")
    return member


def _validate_grocery_arguments(*, arguments, user, household, snapshot):
    list_id, proposed_items = _require_arguments(arguments, ["shopping_list_id", "items"])
    if not isinstance(proposed_items, list) or not 1 <= len(proposed_items) <= 20:
        raise AssistantValidationError("The proposed grocery items are not valid.")
    shopping_list = _validated_active_list(
        list_id=list_id, user=user, household=household, snapshot=snapshot
    )
    items = []
    for proposed_item in proposed_items:
        if not isinstance(proposed_item, dict):
            raise AssistantValidationError("The proposed grocery item is not valid.")
        item_name, quantity, description = _require_arguments(
            proposed_item, ["item_name", "quantity", "description"]
        )
        if not all(isinstance(value, str) for value in (item_name, description)):
            raise AssistantValidationError("The proposed grocery item is not valid.")
        if not _is_integer(quantity) or not 1 <= quantity <= 99:
            raise AssistantValidationError("The proposed grocery quantity is not valid.")
        form = ShoppingItemForm(
            {"text": item_name, "quantity": quantity, "description": description}
        )
        if not form.is_valid():
            raise AssistantValidationError("The proposed grocery item is not valid.")
        items.append(
            {
                "text": form.cleaned_data["text"],
                "quantity": form.cleaned_data["quantity"],
                "description": form.cleaned_data["description"],
            }
        )
    return {
        "shopping_list": shopping_list,
        "items": items,
    }


def _validate_chore_arguments(*, arguments, user, household, snapshot):
    session_id, task_title, assignee_id = _require_arguments(
        arguments, ["chore_session_id", "task_title", "assignee_user_id"]
    )
    if not isinstance(task_title, str) or (
        assignee_id is not None and not _is_integer(assignee_id)
    ):
        raise AssistantValidationError("The proposed chore task is not valid.")
    session = _validated_active_session(
        session_id=session_id, user=user, household=household, snapshot=snapshot
    )
    assignee = _validated_member(
        member_id=assignee_id, household=household, snapshot=snapshot
    )
    form = ChoreTaskForm(
        {"title": task_title, "assignee": assignee.pk if assignee else "", "due_date": ""},
        household=household,
    )
    if not form.is_valid():
        raise AssistantValidationError("The proposed chore task is not valid.")
    return {
        "session": session,
        "title": form.cleaned_data["title"],
        "assignee": assignee,
    }


def _parse_scheduled_for(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 80:
        raise AssistantValidationError("The proposed date and time is not valid.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AssistantValidationError("The proposed date and time is not valid.") from error
    if timezone.is_naive(parsed):
        raise AssistantValidationError("The proposed date and time needs a timezone.")
    return timezone.localtime(parsed)


def _validate_topic_arguments(*, arguments):
    title, notes, scheduled_for = _require_arguments(
        arguments, ["title", "notes", "scheduled_for"]
    )
    if not isinstance(title, str) or not isinstance(notes, str):
        raise AssistantValidationError("The proposed Talk Later topic is not valid.")
    parsed_schedule = _parse_scheduled_for(scheduled_for)
    form_data = {"title": title, "notes": notes, "scheduled_for": ""}
    if parsed_schedule is not None:
        form_data["scheduled_for"] = timezone.localtime(parsed_schedule).strftime(
            "%Y-%m-%dT%H:%M"
        )
    form = DiscussionTopicForm(form_data)
    if not form.is_valid():
        raise AssistantValidationError("The proposed Talk Later topic is not valid.")
    return {
        "title": form.cleaned_data["title"],
        "notes": form.cleaned_data["notes"],
        "scheduled_for": form.cleaned_data["scheduled_for"],
    }


def _candidate_names(context, target_type):
    if target_type == "grocery_list":
        return [item["name"] for item in context["active_grocery_lists"]]
    if target_type == "chore_session":
        return [item["name"] for item in context["active_chore_sessions"]]
    if target_type == "household_member":
        return [item["display_name"] for item in context["household_members"]]
    return []


def _unresolved_details(arguments, context):
    reason, target_type, requested_name, clarification = _require_arguments(
        arguments, ["reason", "target_type", "requested_name", "clarification_question"]
    )
    if (
        reason not in UNRESOLVED_REASONS
        or target_type not in TARGET_TYPES
        or not isinstance(requested_name, str)
        or not isinstance(clarification, str)
        or len(requested_name) > 255
        or len(clarification) > 300
    ):
        raise AssistantValidationError("The assistant response is not valid.")
    target_label = {
        "grocery_list": "grocery list",
        "chore_session": "chore session",
        "household_member": "household member",
        "talk_later": "Talk Later topic",
    }.get(target_type, "requested target")
    if reason in {"unsupported_action", "not_an_addition", "multiple_actions"}:
        message = (
            "I can add multiple grocery items to one list, or one chore task or "
            "Talk Later topic at a time."
        )
    elif reason == "target_not_found":
        message = f"I could not find that {target_label} in your household. Please include the exact name."
    elif reason == "ambiguous_target":
        message = f"I found more than one matching {target_label}. Please include the exact name."
    elif reason == "invalid_datetime":
        message = "Please include a clear future date and time, or leave the reminder unscheduled."
    else:
        message = f"Please include the {target_label} needed for this addition."
    return message, _candidate_names(context, target_type)


def _proposal_from_tool_call(*, tool_call, context, user, household):
    if tool_call.name not in TOOL_NAMES:
        raise AssistantValidationError("The assistant selected an unsupported action.")
    if not isinstance(tool_call.arguments, dict):
        raise AssistantValidationError("The assistant response is not valid.")
    snapshot = context_snapshot(context)
    arguments = tool_call.arguments
    if tool_call.name == "propose_add_grocery_items":
        data = _validate_grocery_arguments(
            arguments=arguments, user=user, household=household, snapshot=snapshot
        )
        preview_items = [
            f"{item['quantity']}× {item['text']}"
            for item in data["items"]
        ]
        return (
            AssistantCommand.ActionType.ADD_GROCERY_ITEM,
            {
                "snapshot": snapshot,
                "shopping_list_id": data["shopping_list"].pk,
                "shopping_list_name": data["shopping_list"].name,
                "items": data["items"],
                "preview_items": preview_items,
            },
        )
    if tool_call.name == "propose_add_chore_task":
        data = _validate_chore_arguments(
            arguments=arguments, user=user, household=household, snapshot=snapshot
        )
        assignee_suffix = (
            f" and assign it to {display_name(data['assignee'])}"
            if data["assignee"]
            else ""
        )
        summary = f"Add {data['title']} to {data['session'].name}{assignee_suffix}."
        return (
            AssistantCommand.ActionType.ADD_CHORE_TASK,
            {
                "snapshot": snapshot,
                "chore_session_id": data["session"].pk,
                "chore_session_name": data["session"].name,
                "title": data["title"],
                "assignee_user_id": data["assignee"].pk if data["assignee"] else None,
                "assignee_name": display_name(data["assignee"]) if data["assignee"] else "",
                "preview_items": [summary],
            },
        )
    if tool_call.name == "propose_add_talk_later_topic":
        data = _validate_topic_arguments(arguments=arguments)
        summary = f"Add {data['title']} to Talk Later."
        if data["scheduled_for"] is not None:
            summary = (
                f"Add {data['title']} to Talk Later for "
                f"{timezone.localtime(data['scheduled_for']).strftime('%d %b, %H:%M')}."
            )
        return (
            AssistantCommand.ActionType.ADD_TALK_LATER_TOPIC,
            {
                "snapshot": snapshot,
                "title": data["title"],
                "notes": data["notes"],
                "scheduled_for": data["scheduled_for"].isoformat()
                if data["scheduled_for"]
                else None,
                "preview_items": [summary],
            },
        )
    return _unresolved_details(arguments, context)


def _rate_limited(user):
    earliest = timezone.now() - timedelta(minutes=1)
    return (
        AssistantCommand.objects.filter(user=user, created_at__gte=earliest).count()
        >= settings.AI_COMMANDS_PER_MINUTE
    )


def _create_or_reuse_command(*, user, household, request_id, source, transcript=""):
    existing = AssistantCommand.objects.filter(
        user=user, household=household, request_id=request_id
    ).first()
    if existing is not None:
        return existing, False
    with transaction.atomic():
        if _rate_limited(user):
            raise AssistantRateLimitError
        try:
            return (
                AssistantCommand.objects.create(
                    user=user,
                    household=household,
                    request_id=request_id,
                    source=source,
                    transcript=transcript,
                    expires_at=timezone.now()
                    + timedelta(seconds=settings.AI_COMMAND_PROPOSAL_TTL_SECONDS),
                ),
                True,
            )
        except IntegrityError:
            return (
                AssistantCommand.objects.get(
                    user=user, household=household, request_id=request_id
                ),
                False,
            )


def _mark_failed(command, error, model_name):
    command.status = AssistantCommand.Status.FAILED
    command.action_type = AssistantCommand.ActionType.NONE
    command.user_message = "I could not understand that command right now. Nothing was added. Please try again."
    command.save(update_fields=["status", "action_type", "user_message"])
    original = getattr(error, "original", error)
    logger.warning(
        "AI command failed command_id=%s user_id=%s status=%s model=%s error=%s",
        command.pk,
        command.user_id,
        command.status,
        model_name,
        original.__class__.__name__,
    )


def _interpret(command):
    context = build_household_context(user=command.user, household=command.household)
    try:
        tool_call = interpret_command(command=command.transcript, context=context)
        result = _proposal_from_tool_call(
            tool_call=tool_call,
            context=context,
            user=command.user,
            household=command.household,
        )
    except (ProviderError, ResponseShapeError, AssistantValidationError) as error:
        _mark_failed(command, error, settings.OPENAI_COMMAND_MODEL)
        return command
    if tool_call.name == "report_unresolved_command":
        message, candidates = result
        command.status = AssistantCommand.Status.UNRESOLVED
        command.action_type = AssistantCommand.ActionType.NONE
        command.user_message = message
        command.proposal = {"candidates": candidates}
        command.save(update_fields=["status", "action_type", "user_message", "proposal"])
        return command
    action_type, proposal = result
    command.status = AssistantCommand.Status.NEEDS_CONFIRMATION
    command.action_type = action_type
    command.proposal = proposal
    command.save(update_fields=["status", "action_type", "proposal"])
    return command


def submit_text_command(*, user, household, request_id, command_text):
    transcript = command_text.strip()
    if not transcript or len(transcript) > MAX_TRANSCRIPT_LENGTH:
        raise AssistantValidationError("Enter a command of 1,000 characters or fewer.")
    command, created = _create_or_reuse_command(
        user=user,
        household=household,
        request_id=request_id,
        source=AssistantCommand.Source.TEXT,
        transcript=transcript,
    )
    return _interpret(command) if created else command


def _audio_content_type(audio):
    return (getattr(audio, "content_type", "") or "").split(";", 1)[0].lower()


def validate_audio(audio):
    if audio is None:
        raise AssistantValidationError("Choose an audio recording first.")
    if _audio_content_type(audio) not in SUPPORTED_AUDIO_TYPES:
        raise AssistantValidationError("Use a WebM, MP4, OGG, WAV, or MPEG audio recording.")
    if getattr(audio, "size", 0) <= 0:
        raise AssistantValidationError("The audio recording is empty.")
    if getattr(audio, "size", 0) > settings.AI_AUDIO_MAX_BYTES:
        raise AssistantValidationError("The audio recording is too large. Please record a shorter command.")


def submit_audio_command(*, user, household, request_id, audio):
    validate_audio(audio)
    command, created = _create_or_reuse_command(
        user=user,
        household=household,
        request_id=request_id,
        source=AssistantCommand.Source.AUDIO,
    )
    if not created:
        return command
    try:
        transcript = transcribe_audio(audio=audio).strip()
        if not transcript or len(transcript) > MAX_TRANSCRIPT_LENGTH:
            raise AssistantValidationError("The recording did not produce a usable command.")
        command.transcript = transcript
        command.save(update_fields=["transcript"])
    except (ProviderError, ResponseShapeError, AssistantValidationError) as error:
        _mark_failed(command, error, settings.OPENAI_TRANSCRIPTION_MODEL)
        return command
    return _interpret(command)


def interpretation_payload(command):
    if command.status == AssistantCommand.Status.NEEDS_CONFIRMATION:
        return {
            "status": "needs_confirmation",
            "command_id": str(command.pk),
            "preview_items": command.proposal.get("preview_items", []),
            "expires_at": command.expires_at.isoformat(),
            "confirm_url": reverse("ai_assistant:confirm", args=[command.pk]),
            "cancel_url": reverse("ai_assistant:cancel", args=[command.pk]),
        }
    if command.status == AssistantCommand.Status.UNRESOLVED:
        return {
            "status": "unresolved",
            "transcript": command.transcript,
            "message": command.user_message,
            "candidates": command.proposal.get("candidates", []),
        }
    if command.status == AssistantCommand.Status.FAILED:
        return {"status": "failed", "message": command.user_message}
    return {"status": "processing", "message": "This command is still being understood."}


def _stored_grocery(command):
    proposal = command.proposal
    snapshot = proposal.get("snapshot", {})
    stored_items = proposal.get("items")
    if isinstance(stored_items, list):
        stored_items = [
            {
                "item_name": item.get("text"),
                "quantity": item.get("quantity"),
                "description": item.get("description"),
            }
            if isinstance(item, dict)
            else item
            for item in stored_items
        ]
    return _validate_grocery_arguments(
        arguments={
            "shopping_list_id": proposal.get("shopping_list_id"),
            "items": stored_items,
        },
        user=command.user,
        household=command.household,
        snapshot=snapshot,
    )


def _stored_chore(command):
    proposal = command.proposal
    return _validate_chore_arguments(
        arguments={
            "chore_session_id": proposal.get("chore_session_id"),
            "task_title": proposal.get("title"),
            "assignee_user_id": proposal.get("assignee_user_id"),
        },
        user=command.user,
        household=command.household,
        snapshot=proposal.get("snapshot", {}),
    )


def _stored_topic(command):
    proposal = command.proposal
    return _validate_topic_arguments(
        arguments={
            "title": proposal.get("title"),
            "notes": proposal.get("notes"),
            "scheduled_for": proposal.get("scheduled_for"),
        }
    )


def _execute(command):
    if command.action_type == AssistantCommand.ActionType.ADD_GROCERY_ITEM:
        data = _stored_grocery(command)
        add_items(
            shopping_list=data["shopping_list"],
            items=data["items"],
            user=command.user,
        )
        item_count = len(data["items"])
        label = (
            f"Added {item_count} item{'s' if item_count != 1 else ''} "
            f"to {data['shopping_list'].name}."
        )
        return label, reverse("shopping:list_detail", args=[data["shopping_list"].pk])
    if command.action_type == AssistantCommand.ActionType.ADD_CHORE_TASK:
        data = _stored_chore(command)
        create_task(
            session=data["session"],
            title=data["title"],
            assignee=data["assignee"],
            user=command.user,
        )
        label = f"Added {data['title']} to {data['session'].name}."
        return label, reverse("chores:session_detail", args=[data["session"].pk])
    if command.action_type == AssistantCommand.ActionType.ADD_TALK_LATER_TOPIC:
        data = _stored_topic(command)
        topic = create_topic(
            household=command.household,
            title=data["title"],
            notes=data["notes"],
            scheduled_for=data["scheduled_for"],
            user=command.user,
        )
        return f"Added {data['title']} to Talk Later.", reverse(
            "talk_later:topic_detail", args=[topic.pk]
        )
    raise AssistantValidationError("This command has no allowed action.")


def confirm_command(*, command_id, user, household):
    with transaction.atomic():
        command = (
            AssistantCommand.objects.select_for_update()
            .filter(pk=command_id, user=user, household=household)
            .first()
        )
        if command is None:
            return None, "not_found"
        if command.status == AssistantCommand.Status.EXECUTED:
            return command, "executed"
        if command.status != AssistantCommand.Status.NEEDS_CONFIRMATION:
            return command, "unavailable"
        if command.expires_at <= timezone.now():
            command.status = AssistantCommand.Status.EXPIRED
            command.save(update_fields=["status"])
            return command, "expired"
        try:
            result_label, result_url = _execute(command)
        except Exception as error:
            command.status = AssistantCommand.Status.FAILED
            command.user_message = "This proposal can no longer be added. Nothing was added. Please submit it again."
            command.save(update_fields=["status", "user_message"])
            logger.warning(
                "AI command confirmation failed command_id=%s user_id=%s status=%s error=%s",
                command.pk,
                command.user_id,
                command.status,
                error.__class__.__name__,
            )
            return command, "failed"
        command.status = AssistantCommand.Status.EXECUTED
        command.executed_at = timezone.now()
        command.result_label = result_label
        command.result_url = result_url
        command.save(
            update_fields=["status", "executed_at", "result_label", "result_url"]
        )
        return command, "executed"


def cancel_command(*, command_id, user, household):
    with transaction.atomic():
        command = (
            AssistantCommand.objects.select_for_update()
            .filter(pk=command_id, user=user, household=household)
            .first()
        )
        if command is None:
            return None, "not_found"
        if command.status == AssistantCommand.Status.NEEDS_CONFIRMATION:
            command.status = AssistantCommand.Status.CANCELLED
            command.save(update_fields=["status"])
            return command, "cancelled"
        return command, "unavailable"
