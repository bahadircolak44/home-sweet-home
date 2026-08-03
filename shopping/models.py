from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from households.models import Household


PURCHASE_HISTORY_DAYS = 7


def purchased_item_history_cutoff(now=None):
    return (now or timezone.now()) - timedelta(days=PURCHASE_HISTORY_DAYS)


class ShoppingListQuerySet(models.QuerySet):
    def available_to(self, user):
        return self.filter(household__memberships__user=user)

    def with_item_counts(self, *, recent_purchases_only=False):
        item_filter = Q()
        if recent_purchases_only:
            item_filter = Q(items__is_purchased=False) | Q(
                items__is_purchased=True,
                items__purchased_at__gte=purchased_item_history_cutoff(),
            )
        return self.annotate(
            item_total=models.Count("items", filter=item_filter),
            purchased_total=models.Count(
                "items",
                filter=(
                    Q(
                        items__is_purchased=True,
                        items__purchased_at__gte=purchased_item_history_cutoff(),
                    )
                    if recent_purchases_only
                    else Q(items__is_purchased=True)
                ),
            ),
            remaining_total=models.Count("items", filter=Q(items__is_purchased=False)),
        )


class ShoppingList(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"

    class ListType(models.TextChoices):
        ALBERT = "ALBERT", "Albert"
        TURKISH_MARKET = "TURKISH_MARKET", "Türk Market"

    ICON_CHOICES = [
        ("🛒", "Shopping cart"),
        ("🇹🇷", "Turkish flag"),
        ("🏠", "Home"),
        ("🐈", "Cat"),
        ("🧴", "Bottle"),
        ("📦", "Package"),
        ("albert-heijn", "Albert Heijn"),
        ("jumbo", "Jumbo"),
    ]

    STORE_ICON_ASSETS = {
        "albert-heijn": "icons/albert-heijn.svg",
        "jumbo": "icons/jumbo.png",
    }

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="shopping_lists"
    )
    name = models.CharField(max_length=120)
    icon = models.CharField(max_length=16, choices=ICON_CHOICES, default="🛒")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    list_type = models.CharField(
        max_length=32, choices=ListType.choices, null=True, blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_shopping_lists",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="completed_shopping_lists",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = ShoppingListQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(
                fields=["household", "status", "-updated_at"],
                name="shopping_active_idx",
            ),
            models.Index(
                fields=["household", "status", "-completed_at"],
                name="shopping_history_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "list_type"], name="shopping_fixed_list_type_unique"
            ),
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
                name="shopping_list_completion_metadata",
            )
        ]

    def __str__(self):
        return f"{self.icon} {self.name}"

    @property
    def is_fixed(self):
        return self.list_type in self.ListType.values

    @property
    def icon_asset(self):
        return self.STORE_ICON_ASSETS.get(self.icon)

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "Enter a list name."})
        completion_is_set = (
            self.completed_at is not None and self.completed_by_id is not None
        )
        if self.status == self.Status.ACTIVE and (
            self.completed_at is not None or self.completed_by_id is not None
        ):
            raise ValidationError("Active lists cannot have completion details.")
        if self.status == self.Status.COMPLETED and not completion_is_set:
            raise ValidationError("Completed lists require completion details.")

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "Enter a list name."})
        return super().save(*args, **kwargs)

    def _count_value(self, annotation_name, purchased=None):
        if hasattr(self, annotation_name):
            return getattr(self, annotation_name)
        queryset = self.items.all()
        if purchased is True:
            queryset = queryset.filter(is_purchased=purchased)
            if self.status == self.Status.ACTIVE:
                queryset = queryset.filter(
                    purchased_at__gte=purchased_item_history_cutoff()
                )
        elif purchased is None and self.status == self.Status.ACTIVE:
            queryset = queryset.filter(
                Q(is_purchased=False)
                | Q(is_purchased=True, purchased_at__gte=purchased_item_history_cutoff())
            )
        return queryset.count()

    @property
    def total_item_count(self):
        return self._count_value("item_total")

    @property
    def purchased_item_count(self):
        return self._count_value("purchased_total", purchased=True)

    @property
    def remaining_item_count(self):
        return self._count_value("remaining_total", purchased=False)

    @property
    def completion_percentage(self):
        if not self.total_item_count:
            return 0
        return round(self.purchased_item_count / self.total_item_count * 100)


class ShoppingItemQuerySet(models.QuerySet):
    def available_to(self, user):
        return self.filter(shopping_list__household__memberships__user=user)


class ShoppingItem(models.Model):
    shopping_list = models.ForeignKey(
        ShoppingList, on_delete=models.CASCADE, related_name="items"
    )
    text = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    description = models.TextField(
        blank=True, default="", validators=[MaxLengthValidator(1000)]
    )
    is_purchased = models.BooleanField(default=False)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="added_shopping_items",
    )
    purchased_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchased_shopping_items",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    purchased_at = models.DateTimeField(null=True, blank=True)

    objects = ShoppingItemQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="shopping_item_quantity_at_least_one",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        is_purchased=False,
                        purchased_at__isnull=True,
                        purchased_by__isnull=True,
                    )
                    | Q(
                        is_purchased=True,
                        purchased_at__isnull=False,
                        purchased_by__isnull=False,
                    )
                ),
                name="shopping_item_purchase_metadata",
            ),
        ]

    def __str__(self):
        return self.text

    def clean(self):
        super().clean()
        self.text = self.text.strip()
        self.description = self.description.strip()
        if not self.text:
            raise ValidationError({"text": "Enter an item."})
        purchase_is_set = (
            self.purchased_at is not None and self.purchased_by_id is not None
        )
        if not self.is_purchased and (
            self.purchased_at is not None or self.purchased_by_id is not None
        ):
            raise ValidationError("Unpurchased items cannot have purchase details.")
        if self.is_purchased and not purchase_is_set:
            raise ValidationError("Purchased items require purchase details.")

    def save(self, *args, **kwargs):
        self.text = self.text.strip()
        self.description = self.description.strip()
        if not self.text:
            raise ValidationError({"text": "Enter an item."})
        return super().save(*args, **kwargs)
