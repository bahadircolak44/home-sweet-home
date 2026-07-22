from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from households.models import Household, HouseholdMembership

from .models import ShoppingItem, ShoppingList


class ShoppingFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.alex = user_model.objects.create_user(
            username="alex", password="test-password", first_name="Alex"
        )
        cls.sam = user_model.objects.create_user(
            username="sam", password="test-password", first_name="Sam"
        )
        cls.outsider = user_model.objects.create_user(
            username="outsider", password="test-password"
        )
        cls.home = Household.objects.create(name="Home")
        cls.other_home = Household.objects.create(name="Other Home")
        HouseholdMembership.objects.create(household=cls.home, user=cls.alex)
        HouseholdMembership.objects.create(household=cls.home, user=cls.sam)
        HouseholdMembership.objects.create(
            household=cls.other_home, user=cls.outsider
        )

    def setUp(self):
        self.shopping_list = ShoppingList.objects.create(
            household=self.home, name="Weekend", icon="🛒", created_by=self.alex
        )

    def test_unauthenticated_user_is_redirected_to_login(self):
        response = self.client.get(reverse("shopping:active_lists"))

        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('shopping:active_lists')}"
        )

    def test_household_members_can_access_the_same_list(self):
        self.client.force_login(self.sam)

        response = self.client.get(
            reverse("shopping:list_detail", args=[self.shopping_list.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Weekend")

    def test_user_outside_household_cannot_access_list(self):
        self.client.force_login(self.outsider)

        response = self.client.get(
            reverse("shopping:list_detail", args=[self.shopping_list.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_adding_item_records_current_user(self):
        self.client.force_login(self.sam)

        response = self.client.post(
            reverse("shopping:item_add", args=[self.shopping_list.pk]),
            {"text": "  Oat milk  "},
        )

        self.assertRedirects(
            response, reverse("shopping:list_detail", args=[self.shopping_list.pk])
        )
        item = ShoppingItem.objects.get(shopping_list=self.shopping_list)
        self.assertEqual(item.text, "Oat milk")
        self.assertEqual(item.added_by, self.sam)

    def test_toggling_item_sets_and_clears_purchase_metadata(self):
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list, text="Bread", added_by=self.alex
        )
        self.client.force_login(self.sam)
        toggle_url = reverse("shopping:item_toggle", args=[item.pk])

        self.client.post(toggle_url)
        item.refresh_from_db()
        self.assertTrue(item.is_purchased)
        self.assertEqual(item.purchased_by, self.sam)
        self.assertIsNotNone(item.purchased_at)

        self.client.post(toggle_url)
        item.refresh_from_db()
        self.assertFalse(item.is_purchased)
        self.assertIsNone(item.purchased_by)
        self.assertIsNone(item.purchased_at)

    def test_completing_list_makes_it_read_only(self):
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list, text="Apples", added_by=self.alex
        )
        self.client.force_login(self.sam)

        self.client.post(
            reverse("shopping:list_complete", args=[self.shopping_list.pk])
        )
        self.shopping_list.refresh_from_db()
        self.assertEqual(self.shopping_list.status, ShoppingList.Status.COMPLETED)
        self.assertEqual(self.shopping_list.completed_by, self.sam)
        self.assertIsNotNone(self.shopping_list.completed_at)

        add_response = self.client.post(
            reverse("shopping:item_add", args=[self.shopping_list.pk]),
            {"text": "Bananas"},
        )
        toggle_response = self.client.post(
            reverse("shopping:item_toggle", args=[item.pk])
        )
        item.refresh_from_db()
        self.assertEqual(add_response.status_code, 404)
        self.assertRedirects(
            toggle_response,
            reverse("shopping:history_detail", args=[self.shopping_list.pk]),
        )
        self.assertFalse(item.is_purchased)

    def test_completed_lists_appear_in_history(self):
        self.client.force_login(self.alex)
        self.client.post(
            reverse("shopping:list_complete", args=[self.shopping_list.pk])
        )

        response = self.client.get(reverse("shopping:history"))

        self.assertContains(response, "Weekend")
        self.assertContains(response, "Completed")
