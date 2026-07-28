import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from shopping.forms import HomeAuthenticationForm

from .models import GoogleAccountConnection
from .oauth import (
    GoogleAccountLinkError,
    GoogleOAuthError,
    authorization_url,
    exchange_authorization_code,
    link_google_identity,
    new_oauth_state,
    resolve_google_identity_user,
    revoke_refresh_token,
    verify_id_token,
)
from .services import sync_household_future_topics, sync_future_topics_for_user

STATE_SESSION_KEY = "google_oauth_state"
NEXT_SESSION_KEY = "google_oauth_next"
MODE_SESSION_KEY = "google_oauth_mode"


def _safe_next_url(request, value):
    if value and url_has_allowed_host_and_scheme(
        url=value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return ""


def _google_enabled_or_404():
    if not settings.GOOGLE_OAUTH_ENABLED:
        raise Http404


class HomeLoginView(auth_views.LoginView):
    authentication_form = HomeAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and not settings.PASSWORD_LOGIN_ENABLED:
            messages.error(request, "Password sign-in is currently unavailable.")
            return redirect("login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["google_oauth_enabled"] = settings.GOOGLE_OAUTH_ENABLED
        context["password_login_enabled"] = settings.PASSWORD_LOGIN_ENABLED
        return context


def start(request):
    _google_enabled_or_404()
    state = new_oauth_state()
    request.session[STATE_SESSION_KEY] = state
    request.session[NEXT_SESSION_KEY] = _safe_next_url(request, request.GET.get("next"))
    request.session[MODE_SESSION_KEY] = "login"
    return redirect(authorization_url(state=state))


@login_required
def reconnect(request):
    _google_enabled_or_404()
    state = new_oauth_state()
    request.session[STATE_SESSION_KEY] = state
    request.session[NEXT_SESSION_KEY] = reverse("google_integration:status")
    request.session[MODE_SESSION_KEY] = "reconnect"
    request.session["google_oauth_reconnect_user_id"] = request.user.pk
    return redirect(authorization_url(state=state, reconnect=True))


def callback(request):
    _google_enabled_or_404()
    expected_state = request.session.pop(STATE_SESSION_KEY, "")
    returned_state = request.GET.get("state", "")
    next_url = request.session.pop(NEXT_SESSION_KEY, "")
    mode = request.session.pop(MODE_SESSION_KEY, "login")
    reconnect_user_id = request.session.pop("google_oauth_reconnect_user_id", None)
    if not expected_state or not secrets.compare_digest(expected_state, returned_state):
        messages.error(request, "Google sign-in could not be verified. Please try again.")
        return redirect("login")
    if request.GET.get("error") or not request.GET.get("code"):
        messages.error(request, "Google sign-in was cancelled or could not be completed.")
        return redirect("login")

    try:
        token_result = exchange_authorization_code(request.GET["code"])
        identity = verify_id_token(token_result.id_token)
        if mode == "reconnect" and reconnect_user_id != resolve_google_identity_user(identity).pk:
            messages.error(request, "Reconnect the Google account linked to your user.")
            return redirect("google_integration:status")
        connection, _created, received_refresh_token = link_google_identity(
            identity=identity, token_result=token_result
        )
    except (GoogleOAuthError, GoogleAccountLinkError):
        messages.error(
            request,
            "This Google account is not linked to a Home Sweet Home user.",
        )
        return redirect("login")

    request.session.cycle_key()
    login(request, connection.user)
    if settings.GOOGLE_CALENDAR_ENABLED and received_refresh_token:
        sync_future_topics_for_user(connection.user)
        for membership in connection.user.household_memberships.select_related("household"):
            sync_household_future_topics(membership.household)
    if not connection.has_refresh_token:
        messages.warning(
            request,
            "Google sign-in succeeded, but Calendar access needs to be reconnected.",
        )
    elif mode == "reconnect":
        messages.success(request, "Google Calendar was reconnected.")
    else:
        messages.success(request, "Signed in with Google.")
    return redirect(_safe_next_url(request, next_url) or settings.LOGIN_REDIRECT_URL)


@login_required
def status(request):
    connection = GoogleAccountConnection.objects.filter(user=request.user).first()
    return render(
        request,
        "google_integration/status.html",
        {
            "connection": connection,
            "google_calendar_enabled": settings.GOOGLE_CALENDAR_ENABLED,
            "google_oauth_enabled": settings.GOOGLE_OAUTH_ENABLED,
        },
    )


@login_required
@require_POST
def disconnect(request):
    if request.POST.get("confirm_disconnect") != "on":
        messages.error(request, "Confirm that you want to disconnect Google Calendar.")
        return redirect("google_integration:status")
    connection = GoogleAccountConnection.objects.filter(user=request.user).first()
    if connection is None:
        messages.info(request, "No Google account is connected.")
        return redirect("google_integration:status")
    revoke_refresh_token(connection)
    connection.delete()
    messages.success(
        request,
        "Google Calendar was disconnected. Existing Calendar events may remain.",
    )
    return redirect("google_integration:status")
