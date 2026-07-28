from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from households.models import HouseholdMembership
from push_notifications.services import schedule_household_notification

from .models import ChoreSession, ChoreTask, ChoreTemplate


class InvalidChoreOperation(Exception):
    pass


def _actor_name(user):
    return _member_name(user)


def _member_name(user):
    return user.get_full_name().strip() or user.get_username()


def _schedule_session_notification(*, session, user, body, url):
    schedule_household_notification(
        household_id=session.household_id,
        actor_user_id=user.pk,
        payload={
            "title": "Home Sweet Home",
            "body": body,
            "url": url,
            "tag": f"chore-session-{session.pk}",
        },
    )


def _member_belongs_to_household(*, household_id, user):
    return user is None or HouseholdMembership.objects.filter(
        household_id=household_id, user_id=user.pk
    ).exists()


def _validate_assignee(*, household_id, assignee):
    if not _member_belongs_to_household(
        household_id=household_id, user=assignee
    ):
        raise InvalidChoreOperation("Choose a member of this household.")


def _validate_template(*, household_id, template):
    if template.household_id != household_id:
        raise InvalidChoreOperation("Choose a template from this household.")


def _assignment_message(*, user, task, assignee):
    actor_name = _actor_name(user)
    if assignee is None:
        return f"{actor_name} added {task.title}."
    return f"{actor_name} assigned {task.title} to {_member_name(assignee)}."


def active_sessions_for_user(user):
    return (
        ChoreSession.objects.available_to(user)
        .filter(status=ChoreSession.Status.ACTIVE)
        .select_related("created_by")
        .with_task_counts()
        .order_by("-updated_at")
    )


def completed_sessions_for_user(user):
    return (
        ChoreSession.objects.available_to(user)
        .filter(status=ChoreSession.Status.COMPLETED)
        .select_related("completed_by")
        .with_task_counts()
        .order_by("-completed_at")
    )


def sessions_for_user(user):
    return ChoreSession.objects.available_to(user).select_related(
        "household", "created_by", "completed_by"
    )


def tasks_for_user(user):
    return ChoreTask.objects.available_to(user).select_related(
        "session", "assignee", "created_by", "completed_by", "source_template"
    )


def templates_for_user(user):
    return ChoreTemplate.objects.filter(
        household__memberships__user=user
    ).select_related("default_assignee", "created_by", "household")


def chore_summary_for_user(user):
    return (
        ChoreSession.objects.available_to(user)
        .filter(status=ChoreSession.Status.ACTIVE)
        .aggregate(
            active_session_count=models.Count("id", distinct=True),
            remaining_task_count=models.Sum(
                "tasks__quantity", filter=models.Q(tasks__is_done=False), default=0
            ),
        )
    )


def touch_session(session_id):
    ChoreSession.objects.filter(pk=session_id).update(updated_at=timezone.now())


@transaction.atomic
def create_session(*, household, name, notes, user):
    return ChoreSession.objects.create(
        household=household,
        name=name,
        notes=notes,
        created_by=user,
    )


@transaction.atomic
def update_session(*, session, name, notes, user):
    locked_session = ChoreSession.objects.select_for_update().get(pk=session.pk)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("Completed sessions are read-only.")
    locked_session.name = name
    locked_session.notes = notes
    locked_session.save(update_fields=["name", "notes", "updated_at"])
    return locked_session


@transaction.atomic
def delete_session(*, session, user):
    locked_session = ChoreSession.objects.select_for_update().get(pk=session.pk)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("Completed sessions are read-only.")
    locked_session.delete()


@transaction.atomic
def complete_session(*, session, user):
    locked_session = ChoreSession.objects.select_for_update().get(pk=session.pk)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("This session has already been completed.")
    now = timezone.now()
    locked_session.status = ChoreSession.Status.COMPLETED
    locked_session.completed_by = user
    locked_session.completed_at = now
    locked_session.updated_at = now
    locked_session.save(
        update_fields=["status", "completed_by", "completed_at", "updated_at"]
    )
    _schedule_session_notification(
        session=locked_session,
        user=user,
        body=f"{_actor_name(user)} completed {locked_session.name}.",
        url=reverse("chores:history_detail", args=[locked_session.pk]),
    )
    return locked_session


@transaction.atomic
def create_task(*, session, title, assignee, user, quantity=1):
    locked_session = ChoreSession.objects.select_for_update().get(pk=session.pk)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("Completed sessions are read-only.")
    _validate_assignee(household_id=locked_session.household_id, assignee=assignee)
    task = ChoreTask.objects.create(
        session=locked_session,
        title=title,
        quantity=quantity,
        assignee=assignee,
        created_by=user,
    )
    touch_session(locked_session.pk)
    _schedule_session_notification(
        session=locked_session,
        user=user,
        body=_assignment_message(user=user, task=task, assignee=assignee),
        url=reverse("chores:session_detail", args=[locked_session.pk]),
    )
    return task


@transaction.atomic
def create_task_from_template(*, session, template, user):
    locked_session = ChoreSession.objects.select_for_update().get(pk=session.pk)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("Completed sessions are read-only.")
    locked_template = ChoreTemplate.objects.select_for_update().get(pk=template.pk)
    _validate_template(household_id=locked_session.household_id, template=locked_template)
    if not locked_template.is_active:
        raise InvalidChoreOperation("This quick-list chore is inactive.")
    if ChoreTask.objects.filter(
        session=locked_session, source_template=locked_template
    ).exists():
        raise InvalidChoreOperation("This quick-list chore has already been added.")
    _validate_assignee(
        household_id=locked_session.household_id,
        assignee=locked_template.default_assignee,
    )
    task = ChoreTask.objects.create(
        session=locked_session,
        title=locked_template.title,
        assignee=locked_template.default_assignee,
        source_template=locked_template,
        created_by=user,
    )
    touch_session(locked_session.pk)
    _schedule_session_notification(
        session=locked_session,
        user=user,
        body=_assignment_message(
            user=user, task=task, assignee=locked_template.default_assignee
        ),
        url=reverse("chores:session_detail", args=[locked_session.pk]),
    )
    return task


@transaction.atomic
def update_task(*, task, title, quantity, assignee, user):
    locked_session = ChoreSession.objects.select_for_update().get(pk=task.session_id)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("Completed sessions are read-only.")
    locked_task = ChoreTask.objects.select_for_update().get(pk=task.pk)
    _validate_assignee(household_id=locked_session.household_id, assignee=assignee)
    assignee_changed = locked_task.assignee_id != getattr(assignee, "pk", None)
    locked_task.title = title
    locked_task.quantity = quantity
    locked_task.assignee = assignee
    locked_task.save(update_fields=["title", "quantity", "assignee", "updated_at"])
    touch_session(locked_session.pk)
    if assignee_changed:
        _schedule_session_notification(
            session=locked_session,
            user=user,
            body=_assignment_message(user=user, task=locked_task, assignee=assignee),
            url=reverse("chores:session_detail", args=[locked_session.pk]),
        )
    return locked_task


@transaction.atomic
def adjust_task_quantity(*, task, delta, user):
    locked_session = ChoreSession.objects.select_for_update().get(pk=task.session_id)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("Completed sessions are read-only.")
    locked_task = ChoreTask.objects.select_for_update().get(pk=task.pk)
    if locked_task.is_done:
        raise InvalidChoreOperation("Completed task quantities cannot be changed.")
    quantity = locked_task.quantity + delta
    if quantity < 1:
        raise InvalidChoreOperation("Task quantity cannot be less than one.")
    locked_task.quantity = quantity
    locked_task.save(update_fields=["quantity", "updated_at"])
    touch_session(locked_session.pk)
    return locked_task


@transaction.atomic
def toggle_task(*, task, user):
    locked_session = ChoreSession.objects.select_for_update().get(pk=task.session_id)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("Completed sessions are read-only.")
    locked_task = ChoreTask.objects.select_for_update().get(pk=task.pk)
    if locked_task.is_done:
        locked_task.is_done = False
        locked_task.completed_by = None
        locked_task.completed_at = None
    else:
        locked_task.is_done = True
        locked_task.completed_by = user
        locked_task.completed_at = timezone.now()
    locked_task.save(
        update_fields=["is_done", "completed_by", "completed_at", "updated_at"]
    )
    touch_session(locked_session.pk)
    if locked_task.is_done:
        _schedule_session_notification(
            session=locked_session,
            user=user,
            body=f"{_actor_name(user)} completed {locked_task.title}.",
            url=reverse("chores:session_detail", args=[locked_session.pk]),
        )
    return locked_task


@transaction.atomic
def delete_task(*, task, user):
    locked_session = ChoreSession.objects.select_for_update().get(pk=task.session_id)
    if locked_session.status != ChoreSession.Status.ACTIVE:
        raise InvalidChoreOperation("Completed sessions are read-only.")
    locked_task = ChoreTask.objects.select_for_update().get(pk=task.pk)
    session_id = locked_session.pk
    locked_task.delete()
    touch_session(session_id)
    return session_id


@transaction.atomic
def create_template(*, household, title, default_assignee, user):
    _validate_assignee(household_id=household.pk, assignee=default_assignee)
    return ChoreTemplate.objects.create(
        household=household,
        title=title,
        default_assignee=default_assignee,
        created_by=user,
    )


@transaction.atomic
def update_template(*, template, title, default_assignee, user):
    locked_template = ChoreTemplate.objects.select_for_update().get(pk=template.pk)
    _validate_assignee(
        household_id=locked_template.household_id, assignee=default_assignee
    )
    locked_template.title = title
    locked_template.default_assignee = default_assignee
    locked_template.save(update_fields=["title", "default_assignee", "updated_at"])
    return locked_template


@transaction.atomic
def set_template_active(*, template, is_active, user):
    locked_template = ChoreTemplate.objects.select_for_update().get(pk=template.pk)
    locked_template.is_active = is_active
    locked_template.save(update_fields=["is_active", "updated_at"])
    return locked_template


def deactivate_template(*, template, user):
    return set_template_active(template=template, is_active=False, user=user)


@transaction.atomic
def delete_template(*, template, user):
    locked_template = ChoreTemplate.objects.select_for_update().get(pk=template.pk)
    if locked_template.tasks.exists():
        locked_template.is_active = False
        locked_template.save(update_fields=["is_active", "updated_at"])
        return "deactivated"
    locked_template.delete()
    return "deleted"
