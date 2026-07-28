import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from households.services import get_household_for_user

from .forms import DiscussionTopicForm
from .services import (
    InvalidDiscussionOperation,
    completed_topics_for_user,
    create_topic,
    delete_topic,
    process_due_reminders,
    toggle_topic,
    topics_for_user,
    upcoming_topics_for_user,
    update_topic,
)
from google_integration.services import calendar_attendee_warning_for_topic, sync_topic_calendar_event

logger = logging.getLogger(__name__)


def _require_household(request):
    household = get_household_for_user(request.user)
    if household is None:
        messages.warning(
            request,
            "Your account is not connected to a household yet. Ask an administrator to add a household membership.",
        )
    return household


def _topic_groups(user):
    now = timezone.now()
    today = timezone.localdate(now)
    last_day = today + timedelta(days=7)
    groups = {
        "Overdue": [],
        "Today": [],
        "Next 7 Days": [],
        "Later": [],
        "Unscheduled": [],
    }
    for topic in upcoming_topics_for_user(user):
        if topic.scheduled_for is None:
            groups["Unscheduled"].append(topic)
            continue
        if topic.scheduled_for < now:
            groups["Overdue"].append(topic)
            continue
        scheduled_date = timezone.localtime(topic.scheduled_for).date()
        if scheduled_date == today:
            groups["Today"].append(topic)
        elif scheduled_date <= last_day:
            groups["Next 7 Days"].append(topic)
        else:
            groups["Later"].append(topic)
    return [(title, topics) for title, topics in groups.items() if topics]


def _index_context(*, request, household, form):
    return {
        "household": household,
        "form": form,
        "now": timezone.now(),
        "topic_groups": _topic_groups(request.user) if household else [],
        "completed_topics": completed_topics_for_user(request.user) if household else [],
    }


@login_required
def topic_index(request):
    household = _require_household(request)
    form = DiscussionTopicForm(request.POST or None)
    if request.method == "POST":
        if household is None:
            return redirect("talk_later:topic_index")
        if form.is_valid():
            topic = create_topic(
                household=household,
                title=form.cleaned_data["title"],
                notes=form.cleaned_data["notes"],
                scheduled_for=form.cleaned_data["scheduled_for"],
                user=request.user,
            )
            messages.success(request, "Topic added to Talk Later.")
            return redirect("talk_later:topic_detail", topic_id=topic.pk)
        return render(
            request,
            "talk_later/topic_index.html",
            _index_context(request=request, household=household, form=form),
            status=422,
        )
    return render(
        request,
        "talk_later/topic_index.html",
        _index_context(request=request, household=household, form=form),
    )


@login_required
def topic_create(request):
    household = _require_household(request)
    if household is None:
        return redirect("talk_later:topic_index")
    form = DiscussionTopicForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        topic = create_topic(
            household=household,
            title=form.cleaned_data["title"],
            notes=form.cleaned_data["notes"],
            scheduled_for=form.cleaned_data["scheduled_for"],
            user=request.user,
        )
        messages.success(request, "Topic added to Talk Later.")
        return redirect("talk_later:topic_detail", topic_id=topic.pk)
    return render(
        request,
        "talk_later/topic_form.html",
        {"form": form, "page_title": "Add Topic", "submit_label": "Add Topic"},
    )


@login_required
def topic_detail(request, topic_id):
    topic = get_object_or_404(topics_for_user(request.user), pk=topic_id)
    return render(
        request,
        "talk_later/topic_detail.html",
        {
            "topic": topic,
            "google_calendar_enabled": settings.GOOGLE_CALENDAR_ENABLED,
            "calendar_attendee_warning": (
                calendar_attendee_warning_for_topic(topic)
                if settings.GOOGLE_CALENDAR_ENABLED and topic.scheduled_for
                else ""
            ),
        },
    )


@login_required
def topic_edit(request, topic_id):
    topic = get_object_or_404(topics_for_user(request.user), pk=topic_id)
    form = DiscussionTopicForm(request.POST or None, instance=topic)
    if request.method == "POST" and form.is_valid():
        try:
            topic = update_topic(
                topic=topic,
                title=form.cleaned_data["title"],
                notes=form.cleaned_data["notes"],
                scheduled_for=form.cleaned_data["scheduled_for"],
                user=request.user,
            )
        except InvalidDiscussionOperation as error:
            messages.error(request, str(error))
            return redirect("talk_later:topic_detail", topic_id=topic.pk)
        messages.success(request, "Talk Later topic updated.")
        return redirect("talk_later:topic_detail", topic_id=topic.pk)
    return render(
        request,
        "talk_later/topic_form.html",
        {
            "form": form,
            "topic": topic,
            "page_title": "Edit Topic",
            "submit_label": "Save Changes",
        },
    )


@login_required
@require_POST
def topic_toggle(request, topic_id):
    topic = get_object_or_404(topics_for_user(request.user), pk=topic_id)
    try:
        topic = toggle_topic(topic=topic, user=request.user)
    except InvalidDiscussionOperation as error:
        messages.error(request, str(error))
        return redirect("talk_later:topic_detail", topic_id=topic.pk)
    messages.success(
        request, "Topic marked done." if topic.is_done else "Topic marked not done."
    )
    next_url = request.POST.get("next")
    if next_url == "index":
        return redirect("talk_later:topic_index")
    return redirect("talk_later:topic_detail", topic_id=topic.pk)


@login_required
def topic_delete(request, topic_id):
    topic = get_object_or_404(topics_for_user(request.user), pk=topic_id)
    if request.method == "POST":
        try:
            delete_topic(topic=topic, user=request.user)
        except InvalidDiscussionOperation as error:
            messages.error(request, str(error))
            return redirect("talk_later:topic_detail", topic_id=topic.pk)
        messages.success(request, "Talk Later topic deleted.")
        return redirect("talk_later:topic_index")
    return render(request, "talk_later/topic_confirm_delete.html", {"topic": topic})


@login_required
@require_POST
def topic_calendar_retry(request, topic_id):
    topic = get_object_or_404(topics_for_user(request.user), pk=topic_id)
    if not settings.GOOGLE_CALENDAR_ENABLED:
        messages.error(request, "Google Calendar integration is not enabled.")
        return redirect("talk_later:topic_detail", topic_id=topic.pk)
    sync_topic_calendar_event(topic)
    topic.refresh_from_db()
    if topic.calendar_sync_status == topic.CalendarSyncStatus.SYNCED:
        messages.success(request, "Google Calendar sync completed.")
    elif topic.calendar_sync_status == topic.CalendarSyncStatus.NOT_SCHEDULED:
        messages.success(request, "Google Calendar event removed.")
    else:
        messages.error(request, topic.calendar_sync_error or "Google Calendar sync failed.")
    return redirect("talk_later:topic_detail", topic_id=topic.pk)


@csrf_exempt
@require_POST
def process_reminders(request):
    expected_token = settings.TALK_LATER_REMINDER_JOB_TOKEN
    provided_token = request.headers.get("X-Reminder-Token", "")
    if not expected_token or not secrets.compare_digest(expected_token, provided_token):
        logger.warning("Rejected Talk Later reminder scheduler request.")
        return JsonResponse({"detail": "Forbidden."}, status=403)
    return JsonResponse(process_due_reminders())
