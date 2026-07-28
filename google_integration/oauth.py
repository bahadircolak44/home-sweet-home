import secrets
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token
from google_auth_oauthlib.flow import Flow

from .crypto import encrypt_refresh_token
from .models import GoogleAccountConnection

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOCATION_URL = "https://oauth2.googleapis.com/revoke"
REQUIRED_SCOPES = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar.events.owned",
)
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleOAuthError(Exception):
    pass


class GoogleAccountLinkError(GoogleOAuthError):
    pass


@dataclass(frozen=True)
class GoogleTokenResult:
    refresh_token: str
    id_token: str
    granted_scopes: list[str]


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    given_name: str = ""
    family_name: str = ""


def new_oauth_state():
    return secrets.token_urlsafe(32)


def authorization_url(*, state, reconnect=False):
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(REQUIRED_SCOPES),
        "state": state,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent" if reconnect else "select_account",
    }
    return f"{GOOGLE_AUTHORIZATION_URL}?{urlencode(params)}"


def exchange_authorization_code(code):
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": GOOGLE_AUTHORIZATION_URL,
            "token_uri": GOOGLE_TOKEN_URL,
        }
    }
    try:
        flow = Flow.from_client_config(client_config, scopes=REQUIRED_SCOPES)
        flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
        flow.fetch_token(code=code)
        token_response = flow.oauth2session.token
        id_token = token_response.get("id_token", "")
        if not id_token:
            raise GoogleOAuthError("Google did not return a valid identity token.")
        raw_scopes = token_response.get("scope", "")
        granted_scopes = (
            raw_scopes.split() if isinstance(raw_scopes, str) else list(raw_scopes or [])
        )
        return GoogleTokenResult(
            refresh_token=flow.credentials.refresh_token or "",
            id_token=id_token,
            granted_scopes=sorted(set(granted_scopes)),
        )
    except GoogleOAuthError:
        raise
    except Exception as error:
        raise GoogleOAuthError("Google sign-in could not be completed.") from error


def verify_id_token(raw_id_token):
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            GoogleRequest(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
        )
    except Exception as error:
        raise GoogleOAuthError("Google identity verification failed.") from error

    email = str(claims.get("email", "")).strip().lower()
    subject = str(claims.get("sub", "")).strip()
    verified = claims.get("email_verified") is True
    expiry = claims.get("exp")
    try:
        is_expired = datetime.fromtimestamp(float(expiry), tz=datetime_timezone.utc) <= datetime.now(
            datetime_timezone.utc
        )
    except (TypeError, ValueError, OSError):
        is_expired = True
    if (
        claims.get("aud") != settings.GOOGLE_OAUTH_CLIENT_ID
        or claims.get("iss") not in GOOGLE_ISSUERS
        or is_expired
        or not subject
        or not email
        or not verified
    ):
        raise GoogleOAuthError("Google identity verification failed.")
    return GoogleIdentity(
        subject=subject,
        email=email,
        email_verified=verified,
        given_name=str(claims.get("given_name", "")).strip(),
        family_name=str(claims.get("family_name", "")).strip(),
    )


def _user_for_identity(identity):
    connection = (
        GoogleAccountConnection.objects.select_related("user")
        .filter(google_subject=identity.subject)
        .first()
    )
    if connection is not None:
        return connection.user, connection, False

    email_connections = list(
        GoogleAccountConnection.objects.select_related("user").filter(email=identity.email)[:2]
    )
    if len(email_connections) > 1:
        raise GoogleAccountLinkError(
            "This Google account is not linked to a Home Sweet Home user."
        )
    if email_connections:
        connection = email_connections[0]
        if connection.google_subject != identity.subject:
            raise GoogleAccountLinkError(
                "This Google account is not linked to a Home Sweet Home user."
            )
        return connection.user, connection, False

    username = settings.GOOGLE_LEGACY_USER_MAP.get(identity.email)
    user_model = get_user_model()
    if username:
        user = user_model.objects.filter(username=username).first()
        if user is None:
            raise GoogleAccountLinkError(
                "This Google account is not linked to a Home Sweet Home user."
            )
        return user, None, True

    users = list(user_model.objects.filter(email__iexact=identity.email)[:2])
    if len(users) != 1:
        raise GoogleAccountLinkError(
            "This Google account is not linked to a Home Sweet Home user."
        )
    return users[0], None, False


def resolve_google_identity_user(identity):
    if not identity.email_verified or identity.email not in settings.GOOGLE_ALLOWED_EMAILS:
        raise GoogleAccountLinkError("This Google account is not approved for Home Sweet Home.")
    user, _connection, _used_legacy_map = _user_for_identity(identity)
    return user


@transaction.atomic
def link_google_identity(*, identity, token_result):
    user = resolve_google_identity_user(identity)
    _resolved_user, matched_connection, used_legacy_map = _user_for_identity(identity)
    connection_for_user = (
        GoogleAccountConnection.objects.select_for_update()
        .select_related("user")
        .filter(user=user)
        .first()
    )
    connection_for_subject = (
        GoogleAccountConnection.objects.select_for_update()
        .select_related("user")
        .filter(google_subject=identity.subject)
        .first()
    )
    if connection_for_user and connection_for_user.google_subject != identity.subject:
        raise GoogleAccountLinkError(
            "This Google account is not linked to a Home Sweet Home user."
        )
    if connection_for_subject and connection_for_subject.user_id != user.pk:
        raise GoogleAccountLinkError(
            "This Google account is not linked to a Home Sweet Home user."
        )

    connection = connection_for_user or connection_for_subject or matched_connection
    created = connection is None
    if connection is None:
        connection = GoogleAccountConnection(user=user, google_subject=identity.subject)

    new_refresh_token = bool(token_result.refresh_token)
    if new_refresh_token:
        connection.encrypted_refresh_token = encrypt_refresh_token(token_result.refresh_token)
        connection.reauthorization_required = False
        connection.last_error = ""
    connection.google_subject = identity.subject
    connection.email = identity.email
    connection.email_verified = True
    connection.granted_scopes = token_result.granted_scopes
    connection.last_login_at = timezone.now()
    connection.save()

    user_updates = []
    if (not user.email or used_legacy_map) and user.email != identity.email:
        user.email = identity.email
        user_updates.append("email")
    if not user.first_name and identity.given_name:
        user.first_name = identity.given_name
        user_updates.append("first_name")
    if not user.last_name and identity.family_name:
        user.last_name = identity.family_name
        user_updates.append("last_name")
    if user_updates:
        user.save(update_fields=user_updates)
    return connection, created, new_refresh_token


def revoke_refresh_token(connection):
    if not connection.encrypted_refresh_token:
        return False
    try:
        from .crypto import decrypt_refresh_token

        payload = urlencode({"token": decrypt_refresh_token(connection.encrypted_refresh_token)}).encode()
        request = Request(GOOGLE_REVOCATION_URL, data=payload, method="POST")
        with urlopen(request, timeout=10) as response:  # nosec B310 - fixed Google URL
            return 200 <= response.status < 300
    except Exception:
        return False
