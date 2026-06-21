"""
Tests for the UI sidebar navigation menu.
"""
from unittest.mock import patch

from django.test import TestCase

from netbox_custom_objects import CustomObjectsPluginConfig
from netbox_custom_objects.navigation import (
    CustomObjectTypeMenuItems,
    _menu_name_groups,
    get_grouped_menu_items,
    uses_group_list_page,
)
from .base import CustomObjectsTestCase


class GetGroupedMenuItemsTest(CustomObjectsTestCase, TestCase):
    """Tests for get_grouped_menu_items() navigation helper."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(CustomObjectsPluginConfig, "should_skip_dynamic_model_creation", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_grouped_cot_appears_in_correct_group(self):
        """A COT with group_name is returned under the matching group label."""
        self.create_custom_object_type(
            name="GroupedObject",
            slug="grouped-object",
            group_name="my-group",
        )

        groups = get_grouped_menu_items()
        group_names = [label for label, _ in groups]

        self.assertIn("my-group", group_names)

    def test_grouped_cot_menu_items_are_lazy(self):
        """The items for a group are a CustomObjectTypeMenuItems instance (queried per access)."""
        self.create_custom_object_type(
            name="GroupedObject",
            slug="grouped-object",
            group_name="my-group",
        )

        groups = get_grouped_menu_items()
        my_group_items = next(items for label, items in groups if label == "my-group")

        self.assertIsInstance(my_group_items, CustomObjectTypeMenuItems)
        self.assertEqual(my_group_items.group_name, "my-group")

    def test_grouped_cot_menu_item_url(self):
        """The menu item yielded for a grouped COT points to the correct list URL."""
        cot = self.create_custom_object_type(
            name="GroupedObject",
            slug="grouped-object",
            group_name="my-group",
        )

        groups = get_grouped_menu_items()
        my_group_items = next(items for label, items in groups if label == "my-group")
        menu_items = list(my_group_items)

        self.assertEqual(len(menu_items), 1)
        self.assertIn(cot.slug, str(menu_items[0].url))

    def test_ungrouped_cot_not_in_grouped_items(self):
        """A COT without a group_name does not appear in get_grouped_menu_items()."""
        self.create_custom_object_type(
            name="UngroupedObject",
            slug="ungrouped-object",
            group_name="",
        )

        groups = get_grouped_menu_items()
        # No groups should be returned for an empty group_name
        self.assertEqual(groups, [])

    def test_multiple_groups_returned(self):
        """COTs with different group names produce separate group entries."""
        self.create_custom_object_type(
            name="GroupedObjectA",
            slug="grouped-object-a",
            group_name="alpha",
        )
        self.create_custom_object_type(
            name="GroupedObjectB",
            slug="grouped-object-b",
            group_name="beta",
        )

        groups = get_grouped_menu_items()
        group_names = [label for label, _ in groups]

        self.assertIn("alpha", group_names)
        self.assertIn("beta", group_names)
        self.assertEqual(len(groups), 2)


class MenuNameGroupNavigationTest(CustomObjectsTestCase, TestCase):
    """Tests for menu_name menus when group_name is also set."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(CustomObjectsPluginConfig, "should_skip_dynamic_model_creation", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_uses_group_list_page_when_both_names_set(self):
        cot = self.create_custom_object_type(
            name="Grouped",
            slug="grouped",
            group_name="Policies",
            menu_name="Security",
        )
        self.assertTrue(uses_group_list_page(cot))

    def test_does_not_use_group_list_page_without_menu_name(self):
        cot = self.create_custom_object_type(
            name="Grouped",
            slug="grouped",
            group_name="Policies",
        )
        self.assertFalse(uses_group_list_page(cot))

    def test_menu_name_group_yields_summary_links_not_cot_entries(self):
        self.create_custom_object_type(
            name="Policy A",
            slug="policy-a",
            group_name="Policies",
            menu_name="Security",
        )
        self.create_custom_object_type(
            name="Policy B",
            slug="policy-b",
            group_name="Policies",
            menu_name="Security",
        )

        groups = _menu_name_groups("Security")
        objects_group = next((items for label, items in groups if label == "Objects"), None)
        self.assertIsNotNone(objects_group)
        menu_items = list(objects_group)
        self.assertEqual(len(menu_items), 1)
        self.assertEqual(menu_items[0].link_text, "Policies")
        self.assertIn("groups/Security/Policies", str(menu_items[0].url))

    def test_menu_name_objects_group_skips_grouped_cots(self):
        self.create_custom_object_type(
            name="Grouped",
            slug="grouped",
            group_name="Policies",
            menu_name="Security",
        )
        ungrouped = self.create_custom_object_type(
            name="Standalone",
            slug="standalone",
            menu_name="Security",
        )

        groups = _menu_name_groups("Security")
        objects_items = next(items for label, items in groups if label == "Objects")
        menu_items = list(objects_items)
        self.assertEqual(len(menu_items), 1)
        self.assertIn(ungrouped.slug, str(menu_items[0].url))

    def test_menu_name_with_group_not_in_stock_menu_groups(self):
        self.create_custom_object_type(
            name="Grouped",
            slug="grouped",
            group_name="Policies",
            menu_name="Security",
        )

        stock_groups = get_grouped_menu_items()
        self.assertEqual(stock_groups, [])

