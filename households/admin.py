from django.contrib import admin

from .models import Household, HouseholdMembership


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(HouseholdMembership)
class HouseholdMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "household", "joined_at")
    list_filter = ("household", "joined_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "household__name")
    autocomplete_fields = ("user", "household")
    readonly_fields = ("joined_at",)
