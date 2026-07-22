from .models import HouseholdMembership


def get_household_for_user(user):
    if not user.is_authenticated:
        return None
    membership = (
        HouseholdMembership.objects.select_related("household")
        .filter(user=user)
        .first()
    )
    return membership.household if membership else None
