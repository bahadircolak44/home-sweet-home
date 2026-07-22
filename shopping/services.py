from django.db import transaction
from django.utils import timezone

from .models import ShoppingItem, ShoppingList


class InvalidShoppingOperation(Exception):
    pass


def active_lists_for_user(user):
    return (
        ShoppingList.objects.available_to(user)
        .filter(status=ShoppingList.Status.ACTIVE)
        .select_related("created_by")
        .with_item_counts()
        .order_by("-updated_at")
    )


def completed_lists_for_user(user):
    return (
        ShoppingList.objects.available_to(user)
        .filter(status=ShoppingList.Status.COMPLETED)
        .select_related("completed_by")
        .with_item_counts()
        .order_by("-completed_at")
    )


def lists_for_user(user):
    return ShoppingList.objects.available_to(user).select_related(
        "household", "created_by", "completed_by"
    )


def items_for_user(user):
    return ShoppingItem.objects.available_to(user).select_related(
        "shopping_list", "added_by", "purchased_by"
    )


def touch_list(shopping_list_id):
    ShoppingList.objects.filter(pk=shopping_list_id).update(updated_at=timezone.now())


@transaction.atomic
def add_item(*, shopping_list, text, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    item = ShoppingItem.objects.create(
        shopping_list=locked_list, text=text, added_by=user
    )
    touch_list(locked_list.pk)
    return item


@transaction.atomic
def toggle_item(*, item, user):
    locked_list = ShoppingList.objects.select_for_update().get(
        pk=item.shopping_list_id
    )
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    locked_item = ShoppingItem.objects.select_for_update().get(pk=item.pk)
    if locked_item.is_purchased:
        locked_item.is_purchased = False
        locked_item.purchased_by = None
        locked_item.purchased_at = None
    else:
        locked_item.is_purchased = True
        locked_item.purchased_by = user
        locked_item.purchased_at = timezone.now()
    locked_item.save(
        update_fields=[
            "is_purchased", "purchased_by", "purchased_at", "updated_at"
        ]
    )
    touch_list(locked_list.pk)
    return locked_item


@transaction.atomic
def delete_item(*, item):
    locked_list = ShoppingList.objects.select_for_update().get(
        pk=item.shopping_list_id
    )
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    locked_item = ShoppingItem.objects.select_for_update().get(pk=item.pk)
    shopping_list_id = locked_list.pk
    locked_item.delete()
    touch_list(shopping_list_id)
    return shopping_list_id


@transaction.atomic
def complete_list(*, shopping_list, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("This list has already been completed.")
    now = timezone.now()
    locked_list.status = ShoppingList.Status.COMPLETED
    locked_list.completed_by = user
    locked_list.completed_at = now
    locked_list.updated_at = now
    locked_list.save(
        update_fields=[
            "status", "completed_by", "completed_at", "updated_at"
        ]
    )
    return locked_list
