from django.contrib import admin

from .models import ShoppingItem, ShoppingList


@admin.register(ShoppingList)
class ShoppingListAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "icon",
        "household",
        "status",
        "created_by",
        "completed_by",
        "updated_at",
    )
    list_filter = ("status", "household", "icon", "created_at", "completed_at")
    search_fields = ("name", "household__name", "created_by__username")
    autocomplete_fields = ("household", "created_by", "completed_by")
    readonly_fields = ("created_at", "updated_at", "completed_at")


@admin.register(ShoppingItem)
class ShoppingItemAdmin(admin.ModelAdmin):
    list_display = (
        "text",
        "shopping_list",
        "is_purchased",
        "added_by",
        "purchased_by",
        "updated_at",
    )
    list_filter = ("is_purchased", "shopping_list__household", "created_at")
    search_fields = ("text", "shopping_list__name", "added_by__username")
    autocomplete_fields = ("shopping_list", "added_by", "purchased_by")
    readonly_fields = ("created_at", "updated_at", "purchased_at")
