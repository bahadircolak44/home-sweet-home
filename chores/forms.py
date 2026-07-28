from django import forms
from django.contrib.auth import get_user_model

from .models import ChoreSession, ChoreTask, ChoreTemplate


def member_name(user):
    return user.get_full_name().strip() or user.get_username()


class HouseholdMemberChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return member_name(user)


def household_members(household):
    return (
        get_user_model()
        .objects.filter(household_memberships__household=household)
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


class ChoreSessionForm(forms.ModelForm):
    notes = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Optional notes for this session..."}
        ),
    )

    class Meta:
        model = ChoreSession
        fields = ("name", "notes")
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Weekend cleaning", "autofocus": True}
            )
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Enter a session name.")
        return name

    def clean_notes(self):
        return self.cleaned_data.get("notes", "").strip()


class ChoreTaskForm(forms.ModelForm):
    assignee = HouseholdMemberChoiceField(
        queryset=None, required=False, empty_label="Unassigned"
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = ChoreTask
        fields = ("title", "assignee", "due_date")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Add a task...",
                    "autocomplete": "off",
                    "data-add-chore-task-input": "",
                }
            ),
            "assignee": forms.Select(),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, household, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = household_members(household)

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Enter a task title.")
        return title


class ChoreTemplateForm(forms.ModelForm):
    default_assignee = HouseholdMemberChoiceField(
        queryset=None, required=False, empty_label="Unassigned"
    )

    class Meta:
        model = ChoreTemplate
        fields = ("title", "default_assignee")
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "Clean the kitchen", "autofocus": True}
            ),
            "default_assignee": forms.Select(),
        }

    def __init__(self, *args, household, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_assignee"].queryset = household_members(household)

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Enter a chore title.")
        return title
