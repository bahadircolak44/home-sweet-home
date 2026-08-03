from django.db import migrations, models


FIXED_GROCERY_LISTS = (
    ("ALBERT", "Albert", "albert-heijn", ("Albert", "Albert Heijn")),
    (
        "TURKISH_MARKET",
        "Türk Market",
        "🇹🇷",
        ("Türk Market", "Turk Market", "Turkish Market"),
    ),
)


def create_fixed_grocery_lists(apps, schema_editor):
    del schema_editor
    Household = apps.get_model("households", "Household")
    HouseholdMembership = apps.get_model("households", "HouseholdMembership")
    ShoppingList = apps.get_model("shopping", "ShoppingList")

    for household in Household.objects.all().iterator():
        creator_id = (
            HouseholdMembership.objects.filter(household_id=household.pk)
            .order_by("pk")
            .values_list("user_id", flat=True)
            .first()
        )
        if creator_id is None:
            continue
        for list_type, name, icon, legacy_names in FIXED_GROCERY_LISTS:
            if ShoppingList.objects.filter(
                household_id=household.pk, list_type=list_type
            ).exists():
                continue
            legacy_list = (
                ShoppingList.objects.filter(
                    household_id=household.pk,
                    status="ACTIVE",
                    list_type__isnull=True,
                    name__in=legacy_names,
                )
                .order_by("pk")
                .first()
            )
            if legacy_list is not None:
                legacy_list.list_type = list_type
                legacy_list.name = name
                legacy_list.icon = icon
                legacy_list.save(update_fields=["list_type", "name", "icon"])
            else:
                ShoppingList.objects.create(
                    household_id=household.pk,
                    list_type=list_type,
                    name=name,
                    icon=icon,
                    created_by_id=creator_id,
                )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("shopping", "0003_alter_shoppinglist_icon"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoppinglist",
            name="list_type",
            field=models.CharField(
                blank=True,
                choices=[("ALBERT", "Albert"), ("TURKISH_MARKET", "Türk Market")],
                max_length=32,
                null=True,
            ),
        ),
        migrations.RunPython(create_fixed_grocery_lists, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="shoppinglist",
            constraint=models.UniqueConstraint(
                fields=("household", "list_type"),
                name="shopping_fixed_list_type_unique",
            ),
        ),
    ]
