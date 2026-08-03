import uuid

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from households.services import get_household_for_user

from .services import (
    AssistantRateLimitError,
    AssistantValidationError,
    cancel_command,
    confirm_command,
    interpretation_payload,
    submit_audio_command,
    submit_text_command,
)


def _error(message, status=400):
    return JsonResponse({"status": "error", "message": message}, status=status)


def _request_id(request):
    try:
        return uuid.UUID(request.POST.get("request_id", ""))
    except (AttributeError, ValueError, TypeError):
        raise AssistantValidationError("A valid request ID is required.")


def _enabled_household(request):
    if not settings.AI_ASSISTANT_ENABLED:
        return None, _error("The AI assistant is not enabled.", status=404)
    household = get_household_for_user(request.user)
    if household is None:
        return None, _error(
            "Your account is not connected to a household yet. Ask an administrator to add a household membership.",
            status=403,
        )
    return household, None


def _interpretation_response(command):
    payload = interpretation_payload(command)
    if payload["status"] == "failed":
        return JsonResponse(payload, status=502)
    if payload["status"] == "processing":
        return JsonResponse(payload, status=202)
    return JsonResponse(payload)


@login_required
@require_POST
def text_command(request):
    household, error = _enabled_household(request)
    if error:
        return error
    try:
        command = submit_text_command(
            user=request.user,
            household=household,
            request_id=_request_id(request),
            command_text=request.POST.get("command", ""),
        )
    except AssistantRateLimitError:
        return _error("Please wait a moment before sending another command.", status=429)
    except AssistantValidationError as validation_error:
        return _error(str(validation_error))
    return _interpretation_response(command)


@login_required
@require_POST
def audio_command(request):
    household, error = _enabled_household(request)
    if error:
        return error
    try:
        command = submit_audio_command(
            user=request.user,
            household=household,
            request_id=_request_id(request),
            audio=request.FILES.get("audio"),
        )
    except AssistantRateLimitError:
        return _error("Please wait a moment before sending another command.", status=429)
    except AssistantValidationError as validation_error:
        return _error(str(validation_error))
    return _interpretation_response(command)


@login_required
@require_POST
def confirm(request, command_id):
    household, error = _enabled_household(request)
    if error:
        return error
    command, outcome = confirm_command(
        command_id=command_id, user=request.user, household=household
    )
    if outcome == "not_found":
        return _error("This proposal was not found.", status=404)
    if outcome == "expired":
        return _error("This proposal expired. Please submit the command again.", status=409)
    if outcome == "failed":
        return _error(command.user_message, status=409)
    if outcome == "unavailable":
        return _error("This proposal is no longer available.", status=409)
    return JsonResponse(
        {
            "status": "executed",
            "message": command.result_label,
            "result_url": command.result_url,
            "result_label": "Open result",
        }
    )


@login_required
@require_POST
def cancel(request, command_id):
    household, error = _enabled_household(request)
    if error:
        return error
    command, outcome = cancel_command(
        command_id=command_id, user=request.user, household=household
    )
    if outcome == "not_found":
        return _error("This proposal was not found.", status=404)
    if outcome != "cancelled":
        return _error("This proposal is no longer available.", status=409)
    return JsonResponse({"status": "cancelled", "message": "Nothing was added."})
