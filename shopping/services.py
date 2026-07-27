from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from push_notifications.services import schedule_household_notification

from .models import ShoppingItem, ShoppingList


class InvalidShoppingOperation(Exception):
    pass


def _actor_name(user):
    return user.get_full_name().strip() or user.get_username()


def _item_label(text, quantity):
    return f"{quantity}× {text}" if quantity > 1 else text


def _schedule_list_notification(*, shopping_list, user, body, url):
    """Build a safe payload before the transaction's commit callback runs."""
    schedule_household_notification(
        household_id=shopping_list.household_id,
        actor_user_id=user.pk,
        payload={
            "title": "Home Sweet Home",
            "body": body,
            "url": url,
            "tag": f"grocery-list-{shopping_list.pk}",
        },
    )


def active_lists_for_user(user):
    return (
        ShoppingList.objects.available_to(user)
        .filter(status=ShoppingList.Status.ACTIVE)
        .select_related("created_by")
        .with_item_counts()
        .order_by("-updated_at")
    )


def grocery_summary_for_user(user):
    return (
        ShoppingList.objects.available_to(user)
        .filter(status=ShoppingList.Status.ACTIVE)
        .aggregate(
            active_list_count=models.Count("id", distinct=True),
            remaining_item_count=models.Count(
                "items", filter=models.Q(items__is_purchased=False)
            ),
        )
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
def create_list(*, household, name, icon, user):
    shopping_list = ShoppingList.objects.create(
        household=household,
        name=name,
        icon=icon,
        created_by=user,
    )
    _schedule_list_notification(
        shopping_list=shopping_list,
        user=user,
        body=f"{_actor_name(user)} created {shopping_list.name}.",
        url=reverse("shopping:list_detail", args=[shopping_list.pk]),
    )
    return shopping_list


@transaction.atomic
def update_list(*, shopping_list, name, icon, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    locked_list.name = name
    locked_list.icon = icon
    locked_list.save(update_fields=["name", "icon", "updated_at"])
    _schedule_list_notification(
        shopping_list=locked_list,
        user=user,
        body=f"{_actor_name(user)} updated {locked_list.name}.",
        url=reverse("shopping:list_detail", args=[locked_list.pk]),
    )
    return locked_list


@transaction.atomic
def delete_list(*, shopping_list, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    household_id = locked_list.household_id
    list_id = locked_list.pk
    list_name = locked_list.name
    locked_list.delete()
    schedule_household_notification(
        household_id=household_id,
        actor_user_id=user.pk,
        payload={
            "title": "Home Sweet Home",
            "body": f"{_actor_name(user)} deleted {list_name}.",
            "url": reverse("shopping:active_lists"),
            "tag": f"grocery-list-{list_id}",
        },
    )


@transaction.atomic
def add_item(*, shopping_list, text, quantity, description, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    item = ShoppingItem.objects.create(
        shopping_list=locked_list,
        text=text,
        quantity=quantity,
        description=description,
        added_by=user,
    )
    touch_list(locked_list.pk)
    _schedule_list_notification(
        shopping_list=locked_list,
        user=user,
        body=(
            f"{_actor_name(user)} added {_item_label(item.text, item.quantity)} "
            f"to {locked_list.name}."
        ),
        url=reverse("shopping:list_detail", args=[locked_list.pk]),
    )
    return item


@transaction.atomic
def update_item(*, item, text, quantity, description, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=item.shopping_list_id)
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    locked_item = ShoppingItem.objects.select_for_update().get(pk=item.pk)
    locked_item.text = text
    locked_item.quantity = quantity
    locked_item.description = description
    locked_item.save(update_fields=["text", "quantity", "description", "updated_at"])
    touch_list(locked_list.pk)
    _schedule_list_notification(
        shopping_list=locked_list,
        user=user,
        body=f"{_actor_name(user)} updated {locked_item.text} in {locked_list.name}.",
        url=reverse("shopping:list_detail", args=[locked_list.pk]),
    )
    return locked_item


@transaction.atomic
def adjust_item_quantity(*, item, delta, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=item.shopping_list_id)
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    locked_item = ShoppingItem.objects.select_for_update().get(pk=item.pk)
    if locked_item.is_purchased:
        raise InvalidShoppingOperation("Purchased items cannot have their quantity changed.")

    quantity = locked_item.quantity + delta
    if quantity < 1:
        raise InvalidShoppingOperation("Item quantity cannot be less than one.")

    locked_item.quantity = quantity
    locked_item.save(update_fields=["quantity", "updated_at"])
    touch_list(locked_list.pk)
    _schedule_list_notification(
        shopping_list=locked_list,
        user=user,
        body=(
            f"{_actor_name(user)} changed the quantity of {locked_item.text} "
            f"to {locked_item.quantity}."
        ),
        url=reverse("shopping:list_detail", args=[locked_list.pk]),
    )
    return locked_item


@transaction.atomic
def toggle_item(*, item, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=item.shopping_list_id)
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
        update_fields=["is_purchased", "purchased_by", "purchased_at", "updated_at"]
    )
    touch_list(locked_list.pk)
    if locked_item.is_purchased:
        body = f"{_actor_name(user)} marked {locked_item.text} as purchased."
    else:
        body = f"{_actor_name(user)} returned {locked_item.text} to remaining items."
    _schedule_list_notification(
        shopping_list=locked_list,
        user=user,
        body=body,
        url=reverse("shopping:list_detail", args=[locked_list.pk]),
    )
    return locked_item


@transaction.atomic
def delete_item(*, item, user):
    locked_list = ShoppingList.objects.select_for_update().get(pk=item.shopping_list_id)
    if locked_list.status != ShoppingList.Status.ACTIVE:
        raise InvalidShoppingOperation("Completed lists are read-only.")
    locked_item = ShoppingItem.objects.select_for_update().get(pk=item.pk)
    shopping_list_id = locked_list.pk
    item_text = locked_item.text
    locked_item.delete()
    touch_list(shopping_list_id)
    _schedule_list_notification(
        shopping_list=locked_list,
        user=user,
        body=f"{_actor_name(user)} removed {item_text} from {locked_list.name}.",
        url=reverse("shopping:list_detail", args=[locked_list.pk]),
    )
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
        update_fields=["status", "completed_by", "completed_at", "updated_at"]
    )
    _schedule_list_notification(
        shopping_list=locked_list,
        user=user,
        body=f"{_actor_name(user)} completed {locked_list.name}.",
        url=reverse("shopping:history_detail", args=[locked_list.pk]),
    )
    return locked_list
