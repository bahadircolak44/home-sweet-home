from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from households.models import Household, HouseholdMembership


class ChoreSessionQuerySet(models.QuerySet):
    def available_to(self, user):
        return self.filter(household__memberships__user=user)

    def with_task_counts(self):
        return self.annotate(
            task_total=models.Count("tasks"),
            done_total=models.Count("tasks", filter=Q(tasks__is_done=True)),
            remaining_total=models.Count("tasks", filter=Q(tasks__is_done=False)),
        )


class ChoreSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="chore_sessions"
    )
    name = models.CharField(max_length=120)
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_chore_sessions",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="completed_chore_sessions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = ChoreSessionQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(
                fields=["household", "status", "-updated_at"],
                name="chores_active_idx",
            ),
            models.Index(
                fields=["household", "status", "-completed_at"],
                name="chores_history_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        status="ACTIVE",
                        completed_at__isnull=True,
                        completed_by__isnull=True,
                    )
                    | Q(
                        status="COMPLETED",
                        completed_at__isnull=False,
                        completed_by__isnull=False,
                    )
                ),
                name="chores_session_completion_metadata",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        self.notes = self.notes.strip()
        if not self.name:
            raise ValidationError({"name": "Enter a session name."})
        completion_is_set = (
            self.completed_at is not None and self.completed_by_id is not None
        )
        if self.status == self.Status.ACTIVE and (
            self.completed_at is not None or self.completed_by_id is not None
        ):
            raise ValidationError("Active sessions cannot have completion details.")
        if self.status == self.Status.COMPLETED and not completion_is_set:
            raise ValidationError("Completed sessions require completion details.")

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        self.notes = self.notes.strip()
        if not self.name:
            raise ValidationError({"name": "Enter a session name."})
        return super().save(*args, **kwargs)

    def _count_value(self, annotation_name, done=None):
        if hasattr(self, annotation_name):
            return getattr(self, annotation_name)
        queryset = self.tasks.all()
        if done is not None:
            queryset = queryset.filter(is_done=done)
        return queryset.count()

    @property
    def total_task_count(self):
        return self._count_value("task_total")

    @property
    def done_task_count(self):
        return self._count_value("done_total", done=True)

    @property
    def remaining_task_count(self):
        return self._count_value("remaining_total", done=False)

    @property
    def completion_percentage(self):
        if not self.total_task_count:
            return 0
        return round(self.done_task_count / self.total_task_count * 100)


class ChoreTemplate(models.Model):
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="chore_templates"
    )
    title = models.CharField(max_length=160)
    default_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="default_chore_templates",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_chore_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(
                fields=["household", "is_active", "title"],
                name="chores_template_active_idx",
            )
        ]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        self.title = self.title.strip()
        if not self.title:
            raise ValidationError({"title": "Enter a chore title."})
        if (
            self.default_assignee_id
            and self.household_id
            and not HouseholdMembership.objects.filter(
                household_id=self.household_id, user_id=self.default_assignee_id
            ).exists()
        ):
            raise ValidationError(
                {"default_assignee": "Choose a member of this household."}
            )

    def save(self, *args, **kwargs):
        self.title = self.title.strip()
        if not self.title:
            raise ValidationError({"title": "Enter a chore title."})
        return super().save(*args, **kwargs)


class ChoreTaskQuerySet(models.QuerySet):
    def available_to(self, user):
        return self.filter(session__household__memberships__user=user)


class ChoreTask(models.Model):
    session = models.ForeignKey(
        ChoreSession, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField(max_length=160)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_chore_tasks",
        null=True,
        blank=True,
    )
    source_template = models.ForeignKey(
        ChoreTemplate,
        on_delete=models.SET_NULL,
        related_name="tasks",
        null=True,
        blank=True,
    )
    is_done = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_chore_tasks",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="completed_chore_tasks",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = ChoreTaskQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "source_template"],
                condition=Q(source_template__isnull=False),
                name="chores_template_once_per_session",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        is_done=False,
                        completed_at__isnull=True,
                        completed_by__isnull=True,
                    )
                    | Q(
                        is_done=True,
                        completed_at__isnull=False,
                        completed_by__isnull=False,
                    )
                ),
                name="chores_task_completion_metadata",
            ),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        self.title = self.title.strip()
        if not self.title:
            raise ValidationError({"title": "Enter a task title."})
        if self.session_id:
            household_id = self.session.household_id
            if self.assignee_id and not HouseholdMembership.objects.filter(
                household_id=household_id, user_id=self.assignee_id
            ).exists():
                raise ValidationError(
                    {"assignee": "Choose a member of this household."}
                )
            if (
                self.source_template_id
                and self.source_template.household_id != household_id
            ):
                raise ValidationError(
                    {"source_template": "Choose a template from this household."}
                )
        completion_is_set = (
            self.completed_at is not None and self.completed_by_id is not None
        )
        if not self.is_done and (
            self.completed_at is not None or self.completed_by_id is not None
        ):
            raise ValidationError("Incomplete tasks cannot have completion details.")
        if self.is_done and not completion_is_set:
            raise ValidationError("Completed tasks require completion details.")

    def save(self, *args, **kwargs):
        self.title = self.title.strip()
        if not self.title:
            raise ValidationError({"title": "Enter a task title."})
        return super().save(*args, **kwargs)
