from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import ShoppingItem, ShoppingList


class HomeAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "Username",
                "autofocus": True,
            }
        )
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "placeholder": "Password"}
        ),
    )


class ShoppingListForm(forms.ModelForm):
    class Meta:
        model = ShoppingList
        fields = ("name", "icon")
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Weekly groceries", "autofocus": True}
            ),
            "icon": forms.RadioSelect,
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Enter a list name.")
        return name


class ShoppingItemForm(forms.ModelForm):
    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(
            attrs={"min": 1, "inputmode": "numeric", "aria-label": "Quantity"}
        ),
    )
    description = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Description or product link...",
                "data-description-input": "",
            }
        ),
    )

    class Meta:
        model = ShoppingItem
        fields = ("text", "quantity", "description")
        labels = {
            "text": "Item name",
            "quantity": "Quantity",
            "description": "Description or product link",
        }
        widgets = {
            "text": forms.TextInput(
                attrs={
                    "placeholder": "Add milk, bread, cat food...",
                    "autocomplete": "off",
                    "data-add-item-input": "",
                }
            )
        }

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if not text:
            raise forms.ValidationError("Enter an item.")
        return text

    def clean_description(self):
        return self.cleaned_data.get("description", "").strip()
