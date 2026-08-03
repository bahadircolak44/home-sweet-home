from django.db import migrations, models


def mark_existing_starter_lists_static(apps, schema_editor):
    del schema_editor
    ShoppingList = apps.get_model("shopping", "ShoppingList")
    ShoppingList.objects.filter(list_type__isnull=False).update(static_list=True)


class Migration(migrations.Migration):
    dependencies = [("shopping", "0004_fixed_grocery_lists")]

    operations = [
        migrations.AddField(
            model_name="shoppinglist",
            name="static_list",
            field=models.BooleanField(
                default=False,
                help_text="Static lists need an extra confirmation before completion.",
            ),
        ),
        migrations.RunPython(mark_existing_starter_lists_static, migrations.RunPython.noop),
    ]
