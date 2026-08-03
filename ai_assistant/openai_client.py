import json
from dataclasses import dataclass

from django.conf import settings

from .prompts import COMMAND_INSTRUCTIONS
from .tools import COMMAND_TOOLS


class ProviderError(Exception):
    def __init__(self, kind, original):
        self.kind = kind
        self.original = original
        super().__init__(kind)


class ResponseShapeError(Exception):
    pass


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


def _get_value(value, name, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _client():
    from openai import OpenAI

    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.AI_COMMAND_TIMEOUT_SECONDS,
        max_retries=1,
    )


def _provider_error(error):
    name = error.__class__.__name__
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return ProviderError("authentication", error)
    if name == "RateLimitError":
        return ProviderError("rate_limit", error)
    if name in {"APITimeoutError", "TimeoutError"}:
        return ProviderError("timeout", error)
    if name == "APIConnectionError":
        return ProviderError("connection", error)
    if name in {"BadRequestError", "UnprocessableEntityError"}:
        return ProviderError("invalid_request", error)
    return ProviderError("provider", error)


def interpret_command(*, command, context):
    """Return one tool call. It is still only a proposal, never an action."""
    user_input = (
        "Authorized household context (JSON):\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        + "\n\nUser command (untrusted text):\n"
        + command
    )
    try:
        response = _client().responses.create(
            model=settings.OPENAI_COMMAND_MODEL,
            instructions=COMMAND_INSTRUCTIONS,
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_input}],
                }
            ],
            tools=COMMAND_TOOLS,
            tool_choice="required",
            parallel_tool_calls=False,
            store=False,
        )
    except Exception as error:
        raise _provider_error(error) from error

    calls = [
        output
        for output in (_get_value(response, "output", []) or [])
        if _get_value(output, "type") == "function_call"
    ]
    if len(calls) != 1:
        raise ResponseShapeError("Expected exactly one function call.")
    name = _get_value(calls[0], "name")
    arguments = _get_value(calls[0], "arguments")
    if not isinstance(name, str) or not isinstance(arguments, str):
        raise ResponseShapeError("Function call was malformed.")
    try:
        parsed_arguments = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise ResponseShapeError("Function arguments were not JSON.") from error
    if not isinstance(parsed_arguments, dict):
        raise ResponseShapeError("Function arguments must be an object.")
    return ToolCall(name=name, arguments=parsed_arguments)


def transcribe_audio(*, audio):
    """Adapt Django's upload wrapper to the SDK's supported file tuple format.

    The service has already enforced the small upload limit. Reading it here keeps
    the file transient: it is sent in this request only and is never persisted.
    """
    try:
        audio.seek(0)
    except (AttributeError, OSError):
        pass
    filename = getattr(audio, "name", "quick-add-audio.webm") or "quick-add-audio.webm"
    content_type = getattr(audio, "content_type", "") or "application/octet-stream"
    try:
        file = (filename, audio.read(), content_type)
    except Exception as error:
        raise _provider_error(error) from error
    try:
        result = _client().audio.transcriptions.create(
            model=settings.OPENAI_TRANSCRIPTION_MODEL,
            file=file,
        )
    except Exception as error:
        raise _provider_error(error) from error
    transcript = _get_value(result, "text")
    if not isinstance(transcript, str):
        raise ResponseShapeError("Transcription response did not contain text.")
    return transcript
