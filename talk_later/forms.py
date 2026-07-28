from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import DiscussionTopic


class DiscussionTopicForm(forms.ModelForm):
    notes = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(
            attrs={"rows": 4, "placeholder": "Optional details to discuss..."}
        ),
    )
    scheduled_for = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        ),
    )

    class Meta:
        model = DiscussionTopic
        fields = ("title", "notes", "scheduled_for")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Discuss the holiday budget",
                    "autocomplete": "off",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.scheduled_for and not self.is_bound:
            self.initial["scheduled_for"] = timezone.localtime(
                self.instance.scheduled_for
            ).strftime("%Y-%m-%dT%H:%M")

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Enter a topic title.")
        return title

    def clean_notes(self):
        return self.cleaned_data.get("notes", "").strip()

    def clean_scheduled_for(self):
        scheduled_for = self.cleaned_data.get("scheduled_for")
        if scheduled_for is None:
            return None

        existing_schedule = self.instance.scheduled_for if self.instance.pk else None
        schedule_changed = scheduled_for != existing_schedule
        if (
            (not self.instance.pk or schedule_changed)
            and scheduled_for < timezone.now() - timedelta(minutes=1)
        ):
            raise forms.ValidationError(
                "Choose a future date and time, or leave the reminder empty."
            )
        return scheduled_for
