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
        HouseholdMembership.objects.create(household=cls.other_home, user=cls.outsider)

    def setUp(self):
        self.shopping_list = ShoppingList.objects.create(
            household=self.home, name="Weekend", icon="🛒", created_by=self.alex
        )

    def test_unauthenticated_user_is_redirected_to_login(self):
        response = self.client.get(reverse("home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_dashboard_and_grocery_module_routes_are_available(self):
        ShoppingItem.objects.create(
            shopping_list=self.shopping_list, text="Bread", added_by=self.alex
        )
        self.client.force_login(self.alex)

        dashboard = self.client.get(reverse("home"))
        groceries = self.client.get(reverse("shopping:active_lists"))
        service_worker = self.client.get(reverse("service_worker"))

        self.assertEqual(reverse("shopping:active_lists"), "/groceries/")
        self.assertContains(dashboard, "Everything your household needs")
        self.assertContains(dashboard, "active list")
        self.assertContains(dashboard, "item remaining")
        self.assertContains(dashboard, "Household Chores")
        self.assertContains(dashboard, "Work in Progress")
        self.assertEqual(groceries.status_code, 200)
        self.assertEqual(service_worker.status_code, 200)
        self.assertEqual(service_worker["Service-Worker-Allowed"], "/")

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

    def test_quantity_defaults_to_one_and_add_records_current_user(self):
        default_item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list, text="Bread", added_by=self.alex
        )
        self.assertEqual(default_item.quantity, 1)
        self.client.force_login(self.sam)

        response = self.client.post(
            reverse("shopping:item_add", args=[self.shopping_list.pk]),
            {"text": "  Oat milk  ", "quantity": 1, "description": ""},
        )

        self.assertRedirects(
            response, reverse("shopping:list_detail", args=[self.shopping_list.pk])
        )
        item = ShoppingItem.objects.get(
            shopping_list=self.shopping_list, text="Oat milk"
        )
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.added_by, self.sam)

        detail = self.client.get(
            reverse("shopping:list_detail", args=[self.shopping_list.pk])
        )
        self.assertContains(detail, "1×", count=2)

    def test_quantity_rejects_zero_and_negative_values(self):
        self.client.force_login(self.alex)
        add_url = reverse("shopping:item_add", args=[self.shopping_list.pk])

        for quantity in (0, -1):
            with self.subTest(quantity=quantity):
                response = self.client.post(
                    add_url,
                    {"text": "Invalid quantity", "quantity": quantity},
                )
                self.assertEqual(response.status_code, 422)
                self.assertContains(
                    response,
                    "Ensure this value is greater than or equal to 1.",
                    status_code=422,
                )
        self.assertFalse(ShoppingItem.objects.filter(text="Invalid quantity").exists())

    def test_description_is_trimmed_linked_and_safely_displayed(self):
        self.client.force_login(self.alex)
        description = "  <script>alert('no')</script>\nhttps://example.com/product  "

        self.client.post(
            reverse("shopping:item_add", args=[self.shopping_list.pk]),
            {"text": "Cat food", "quantity": 2, "description": description},
        )
        item = ShoppingItem.objects.get(text="Cat food")
        response = self.client.get(
            reverse("shopping:list_detail", args=[self.shopping_list.pk])
        )

        self.assertEqual(
            item.description,
            "<script>alert('no')</script>\nhttps://example.com/product",
        )
        self.assertContains(response, "2×")
        self.assertNotContains(response, "<script>")
        self.assertContains(response, "&lt;script&gt;")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertContains(response, "data-description-input")

    def test_active_item_can_be_edited(self):
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list, text="Milk", added_by=self.alex
        )
        original_list_update = self.shopping_list.updated_at
        self.client.force_login(self.sam)

        edit_page = self.client.get(reverse("shopping:item_edit", args=[item.pk]))
        self.assertContains(edit_page, "Edit Grocery Item")

        response = self.client.post(
            reverse("shopping:item_edit", args=[item.pk]),
            {
                "text": "Sparkling water",
                "quantity": 6,
                "description": "Green bottles",
            },
        )

        self.assertRedirects(
            response, reverse("shopping:list_detail", args=[self.shopping_list.pk])
        )
        item.refresh_from_db()
        self.shopping_list.refresh_from_db()
        self.assertEqual(item.text, "Sparkling water")
        self.assertEqual(item.quantity, 6)
        self.assertEqual(item.description, "Green bottles")
        self.assertGreater(self.shopping_list.updated_at, original_list_update)

    def test_toggling_item_sets_and_clears_purchase_metadata(self):
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list,
            text="Bread",
            quantity=4,
            added_by=self.alex,
        )
        self.client.force_login(self.sam)
        toggle_url = reverse("shopping:item_toggle", args=[item.pk])

        self.client.post(toggle_url)
        item.refresh_from_db()
        self.assertTrue(item.is_purchased)
        self.assertEqual(item.purchased_by, self.sam)
        self.assertIsNotNone(item.purchased_at)
        purchased_view = self.client.get(
            reverse("shopping:list_detail", args=[self.shopping_list.pk])
        )
        self.assertContains(purchased_view, "Purchased")
        self.assertContains(purchased_view, "4×")

        self.client.post(toggle_url)
        item.refresh_from_db()
        self.assertFalse(item.is_purchased)
        self.assertIsNone(item.purchased_by)
        self.assertIsNone(item.purchased_at)

    def test_completed_list_is_read_only_and_appears_in_history(self):
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list,
            text="Apples",
            quantity=3,
            description="https://example.com/apples",
            added_by=self.alex,
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
            {"text": "Bananas", "quantity": 1},
        )
        edit_response = self.client.get(reverse("shopping:item_edit", args=[item.pk]))
        history = self.client.get(
            reverse("shopping:history_detail", args=[self.shopping_list.pk])
        )

        self.assertEqual(add_response.status_code, 404)
        self.assertEqual(edit_response.status_code, 404)
        self.assertContains(history, "Apples")
        self.assertContains(history, "3×")
        self.assertContains(history, 'target="_blank"')
