from django.conf import settings
from django.db import models


class Household(models.Model):
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class HouseholdMembership(models.Model):
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="household_memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["household__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "user"], name="unique_household_membership"
            )
        ]

    def __str__(self):
        return f"{self.user} in {self.household}"
