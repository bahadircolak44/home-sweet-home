from django.contrib.auth import get_user_model
from django.utils import timezone

from chores.services import active_sessions_for_user
from shopping.services import active_lists_for_user


def display_name(user):
    return user.get_full_name().strip() or user.get_username()


def build_household_context(*, user, household):
    """Return the smallest useful, already-authorized command context."""
    grocery_lists = list(
        active_lists_for_user(user)
        .filter(household=household)
        .values("id", "name")
    )
    chore_sessions = list(
        active_sessions_for_user(user)
        .filter(household=household)
        .values("id", "name")
    )
    members = list(
        get_user_model()
        .objects.filter(household_memberships__household=household)
        .distinct()
        .order_by("first_name", "last_name", "username")
    )
    return {
        "current_time": timezone.localtime(timezone.now()).isoformat(),
        "timezone": timezone.get_current_timezone_name(),
        "active_grocery_lists": grocery_lists,
        "active_chore_sessions": chore_sessions,
        "household_members": [
            {
                "id": member.pk,
                "display_name": display_name(member),
                "username": member.get_username(),
            }
            for member in members
        ],
    }


def context_snapshot(context):
    """Keep only authorized IDs with the proposal; never retain extra context."""
    return {
        "grocery_list_ids": [item["id"] for item in context["active_grocery_lists"]],
        "chore_session_ids": [item["id"] for item in context["active_chore_sessions"]],
        "household_member_ids": [item["id"] for item in context["household_members"]],
    }
