from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from households.models import HouseholdMembership
from households.services import get_household_for_user

from .forms import ChoreSessionForm, ChoreTaskForm, ChoreTemplateForm, member_name
from .models import ChoreSession, ChoreTemplate
from .services import (
    InvalidChoreOperation,
    active_sessions_for_user,
    adjust_task_quantity,
    completed_sessions_for_user,
    complete_session,
    create_session,
    create_task,
    create_task_from_template,
    create_template,
    deactivate_template,
    delete_session,
    delete_task,
    delete_template,
    sessions_for_user,
    set_template_active,
    tasks_for_user,
    templates_for_user,
    toggle_task,
    update_session,
    update_task,
    update_template,
)


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _require_household(request):
    household = get_household_for_user(request.user)
    if household is None:
        messages.warning(
            request,
            "Your account is not connected to a household yet. Ask an administrator to add a household membership.",
        )
    return household


def _task_groups(session, done=None):
    tasks_queryset = session.tasks.select_related(
        "assignee", "created_by", "completed_by"
    )
    if done is not None:
        tasks_queryset = tasks_queryset.filter(is_done=done)
    tasks = list(tasks_queryset.order_by("created_at"))
    tasks_by_assignee = {}
    unassigned_tasks = []
    for task in tasks:
        if task.assignee_id is None:
            unassigned_tasks.append(task)
        else:
            tasks_by_assignee.setdefault(task.assignee_id, []).append(task)

    members = (
        HouseholdMembership.objects.filter(household_id=session.household_id)
        .select_related("user")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    groups = []
    for membership in members:
        member_tasks = tasks_by_assignee.get(membership.user_id, [])
        if not member_tasks:
            continue
        done_count = sum(task.quantity for task in member_tasks if task.is_done)
        total_count = sum(task.quantity for task in member_tasks)
        groups.append(
            {
                "title": member_name(membership.user),
                "tasks": member_tasks,
                "done_count": done_count,
                "total_count": total_count,
                "percentage": round(done_count / total_count * 100),
            }
        )
    if unassigned_tasks:
        done_count = sum(task.quantity for task in unassigned_tasks if task.is_done)
        total_count = sum(task.quantity for task in unassigned_tasks)
        groups.append(
            {
                "title": "Unassigned",
                "tasks": unassigned_tasks,
                "done_count": done_count,
                "total_count": total_count,
                "percentage": round(done_count / total_count * 100),
            }
        )
    return groups


def _session_context(session, task_form=None, quick_add_error=None):
    refreshed_session = (
        ChoreSession.objects.with_task_counts()
        .select_related("household", "created_by", "completed_by")
        .get(pk=session.pk)
    )
    quick_templates = list(
        ChoreTemplate.objects.filter(
            household_id=refreshed_session.household_id, is_active=True
        )
        .select_related("default_assignee")
        .order_by("title")
    )
    added_template_ids = set(
        refreshed_session.tasks.exclude(source_template__isnull=True).values_list(
            "source_template_id", flat=True
        )
    )
    return {
        "session": refreshed_session,
        "task_form": task_form
        or ChoreTaskForm(household=refreshed_session.household),
        "task_groups": _task_groups(refreshed_session, done=False),
        "completed_tasks": list(
            refreshed_session.tasks.filter(is_done=True)
            .select_related("assignee", "created_by", "completed_by")
            .order_by("-completed_at")
        ),
        "quick_templates": quick_templates,
        "added_template_ids": added_template_ids,
        "quick_add_error": quick_add_error,
    }


@login_required
def session_index(request):
    household = get_household_for_user(request.user)
    return render(
        request,
        "chores/session_index.html",
        {
            "household": household,
            "sessions": active_sessions_for_user(request.user) if household else [],
        },
    )


@login_required
def session_create(request):
    household = _require_household(request)
    if household is None:
        return redirect("chores:session_index")
    initial = None
    if request.method != "POST":
        initial = {"name": f"Week of {date.today():%-d %B %Y}"}
    form = ChoreSessionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        session = create_session(
            household=household,
            name=form.cleaned_data["name"],
            notes=form.cleaned_data["notes"],
            user=request.user,
        )
        messages.success(request, "Chore session created.")
        return redirect("chores:session_detail", session_id=session.pk)
    return render(
        request,
        "chores/session_form.html",
        {"form": form, "page_title": "New Chore Session", "submit_label": "Create Session"},
    )


@login_required
def session_detail(request, session_id):
    session = get_object_or_404(
        sessions_for_user(request.user).filter(status=ChoreSession.Status.ACTIVE),
        pk=session_id,
    )
    return render(request, "chores/session_detail.html", _session_context(session))


@login_required
def session_edit(request, session_id):
    session = get_object_or_404(
        sessions_for_user(request.user).filter(status=ChoreSession.Status.ACTIVE),
        pk=session_id,
    )
    form = ChoreSessionForm(request.POST or None, instance=session)
    if request.method == "POST" and form.is_valid():
        try:
            session = update_session(
                session=session,
                name=form.cleaned_data["name"],
                notes=form.cleaned_data["notes"],
                user=request.user,
            )
        except InvalidChoreOperation as error:
            messages.error(request, str(error))
            return redirect("chores:history_detail", session_id=session.pk)
        messages.success(request, "Chore session updated.")
        return redirect("chores:session_detail", session_id=session.pk)
    return render(
        request,
        "chores/session_form.html",
        {
            "form": form,
            "page_title": "Edit Chore Session",
            "submit_label": "Save Changes",
            "session": session,
        },
    )


@login_required
def session_delete(request, session_id):
    session = get_object_or_404(
        sessions_for_user(request.user).filter(status=ChoreSession.Status.ACTIVE),
        pk=session_id,
    )
    if request.method == "POST":
        try:
            delete_session(session=session, user=request.user)
        except InvalidChoreOperation as error:
            messages.error(request, str(error))
            return redirect("chores:history_detail", session_id=session.pk)
        messages.success(request, "Chore session deleted.")
        return redirect("chores:session_index")
    return render(request, "chores/session_confirm_delete.html", {"session": session})


@login_required
def session_complete(request, session_id):
    session = get_object_or_404(
        sessions_for_user(request.user).filter(status=ChoreSession.Status.ACTIVE),
        pk=session_id,
    )
    session = ChoreSession.objects.with_task_counts().get(pk=session.pk)
    if request.method == "POST":
        try:
            completed = complete_session(session=session, user=request.user)
        except InvalidChoreOperation as error:
            messages.error(request, str(error))
            return redirect("chores:history_detail", session_id=session.pk)
        messages.success(request, "Chore session completed. It is now in history.")
        return redirect("chores:history_detail", session_id=completed.pk)
    return render(request, "chores/session_complete_confirmation.html", {"session": session})


@login_required
@require_POST
def task_add(request, session_id):
    session = get_object_or_404(
        sessions_for_user(request.user).filter(status=ChoreSession.Status.ACTIVE),
        pk=session_id,
    )
    form = ChoreTaskForm(request.POST, household=session.household)
    if form.is_valid():
        try:
            create_task(
                session=session,
                title=form.cleaned_data["title"],
                quantity=form.cleaned_data["quantity"],
                assignee=form.cleaned_data["assignee"],
                user=request.user,
            )
        except InvalidChoreOperation as error:
            messages.error(request, str(error))
            return redirect("chores:session_detail", session_id=session.pk)
        if _is_htmx(request):
            return render(
                request,
                "chores/partials/session_interactions.html",
                _session_context(session),
            )
        return redirect("chores:session_detail", session_id=session.pk)
    context = _session_context(session, task_form=form)
    if _is_htmx(request):
        return render(
            request,
            "chores/partials/session_interactions.html",
            context,
            status=422,
        )
    return render(request, "chores/session_detail.html", context, status=422)


@login_required
@require_POST
def task_quick_add(request, session_id, template_id):
    session = get_object_or_404(
        sessions_for_user(request.user).filter(status=ChoreSession.Status.ACTIVE),
        pk=session_id,
    )
    template = get_object_or_404(
        templates_for_user(request.user).filter(is_active=True), pk=template_id
    )
    try:
        create_task_from_template(session=session, template=template, user=request.user)
    except InvalidChoreOperation as error:
        if _is_htmx(request):
            return render(
                request,
                "chores/partials/session_interactions.html",
                _session_context(session, quick_add_error=str(error)),
                status=422,
            )
        messages.error(request, str(error))
        return redirect("chores:session_detail", session_id=session.pk)
    if _is_htmx(request):
        return render(
            request,
            "chores/partials/session_interactions.html",
            _session_context(session),
        )
    return redirect("chores:session_detail", session_id=session.pk)


@login_required
@require_POST
def task_toggle(request, task_id):
    task = get_object_or_404(tasks_for_user(request.user), pk=task_id)
    session = task.session
    try:
        toggle_task(task=task, user=request.user)
    except InvalidChoreOperation as error:
        messages.error(request, str(error))
        destination = (
            "chores:history_detail"
            if session.status == ChoreSession.Status.COMPLETED
            else "chores:session_detail"
        )
        return redirect(destination, session_id=session.pk)
    if _is_htmx(request):
        return render(
            request,
            "chores/partials/session_interactions.html",
            _session_context(session),
        )
    return redirect("chores:session_detail", session_id=session.pk)


@login_required
@require_POST
def task_quantity_adjust(request, task_id):
    try:
        delta = int(request.POST.get("delta", ""))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Quantity adjustment must be a whole number.")
    if delta not in (-1, 1):
        return HttpResponseBadRequest("Quantity adjustment must be one step at a time.")

    task = get_object_or_404(tasks_for_user(request.user), pk=task_id)
    session = task.session
    try:
        adjust_task_quantity(task=task, delta=delta, user=request.user)
    except InvalidChoreOperation as error:
        messages.error(request, str(error))
        destination = (
            "chores:history_detail"
            if session.status == ChoreSession.Status.COMPLETED
            else "chores:session_detail"
        )
        return redirect(destination, session_id=session.pk)
    if _is_htmx(request):
        return render(
            request,
            "chores/partials/session_interactions.html",
            _session_context(session),
        )
    return redirect("chores:session_detail", session_id=session.pk)


@login_required
def task_edit(request, task_id):
    task = get_object_or_404(
        tasks_for_user(request.user).filter(
            session__status=ChoreSession.Status.ACTIVE
        ),
        pk=task_id,
    )
    form = ChoreTaskForm(request.POST or None, instance=task, household=task.session.household)
    if request.method == "POST" and form.is_valid():
        try:
            task = update_task(
                task=task,
                title=form.cleaned_data["title"],
                quantity=form.cleaned_data["quantity"],
                assignee=form.cleaned_data["assignee"],
                user=request.user,
            )
        except InvalidChoreOperation as error:
            messages.error(request, str(error))
            return redirect("chores:history_detail", session_id=task.session_id)
        messages.success(request, "Chore task updated.")
        return redirect("chores:session_detail", session_id=task.session_id)
    return render(
        request,
        "chores/task_form.html",
        {"form": form, "task": task, "session": task.session},
    )


@login_required
@require_POST
def task_delete(request, task_id):
    task = get_object_or_404(tasks_for_user(request.user), pk=task_id)
    session = task.session
    try:
        delete_task(task=task, user=request.user)
    except InvalidChoreOperation as error:
        messages.error(request, str(error))
        destination = (
            "chores:history_detail"
            if session.status == ChoreSession.Status.COMPLETED
            else "chores:session_detail"
        )
        return redirect(destination, session_id=session.pk)
    if _is_htmx(request):
        return render(
            request,
            "chores/partials/session_interactions.html",
            _session_context(session),
        )
    return redirect("chores:session_detail", session_id=session.pk)


@login_required
def quick_list(request):
    household = get_household_for_user(request.user)
    return render(
        request,
        "chores/quick_list.html",
        {
            "household": household,
            "templates": templates_for_user(request.user) if household else [],
        },
    )


@login_required
def template_create(request):
    household = _require_household(request)
    if household is None:
        return redirect("chores:quick_list")
    form = ChoreTemplateForm(request.POST or None, household=household)
    if request.method == "POST" and form.is_valid():
        try:
            create_template(
                household=household,
                title=form.cleaned_data["title"],
                default_assignee=form.cleaned_data["default_assignee"],
                user=request.user,
            )
        except InvalidChoreOperation as error:
            form.add_error("default_assignee", str(error))
        else:
            messages.success(request, "Quick-list chore created.")
            return redirect("chores:quick_list")
    return render(
        request,
        "chores/template_form.html",
        {"form": form, "page_title": "New Quick-List Chore", "submit_label": "Create Chore"},
    )


@login_required
def template_edit(request, template_id):
    template = get_object_or_404(templates_for_user(request.user), pk=template_id)
    form = ChoreTemplateForm(
        request.POST or None, instance=template, household=template.household
    )
    if request.method == "POST" and form.is_valid():
        try:
            update_template(
                template=template,
                title=form.cleaned_data["title"],
                default_assignee=form.cleaned_data["default_assignee"],
                user=request.user,
            )
        except InvalidChoreOperation as error:
            form.add_error("default_assignee", str(error))
        else:
            messages.success(request, "Quick-list chore updated.")
            return redirect("chores:quick_list")
    return render(
        request,
        "chores/template_form.html",
        {
            "form": form,
            "page_title": "Edit Quick-List Chore",
            "submit_label": "Save Changes",
            "template": template,
        },
    )


@login_required
@require_POST
def template_toggle_active(request, template_id):
    template = get_object_or_404(templates_for_user(request.user), pk=template_id)
    if template.is_active:
        deactivate_template(template=template, user=request.user)
        messages.success(request, "Quick-list chore deactivated.")
    else:
        set_template_active(template=template, is_active=True, user=request.user)
        messages.success(request, "Quick-list chore activated.")
    return redirect("chores:quick_list")


@login_required
def template_delete(request, template_id):
    template = get_object_or_404(templates_for_user(request.user), pk=template_id)
    if request.method == "POST":
        outcome = delete_template(template=template, user=request.user)
        if outcome == "deactivated":
            messages.success(
                request,
                "This quick-list chore was used before, so it has been deactivated.",
            )
        else:
            messages.success(request, "Quick-list chore deleted.")
        return redirect("chores:quick_list")
    return render(request, "chores/template_confirm_delete.html", {"template": template})


@login_required
def history(request):
    household = get_household_for_user(request.user)
    return render(
        request,
        "chores/history.html",
        {
            "household": household,
            "sessions": completed_sessions_for_user(request.user) if household else [],
        },
    )


@login_required
def history_detail(request, session_id):
    session = get_object_or_404(
        sessions_for_user(request.user).filter(status=ChoreSession.Status.COMPLETED),
        pk=session_id,
    )
    session = ChoreSession.objects.with_task_counts().select_related(
        "completed_by"
    ).get(pk=session.pk)
    return render(
        request,
        "chores/history_detail.html",
        {"session": session, "task_groups": _task_groups(session)},
    )
