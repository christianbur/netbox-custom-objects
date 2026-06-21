"""Tests for CustomObjectType group summary list views."""

from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.urls import reverse
from utilities.testing import create_test_user

from netbox_custom_objects import CustomObjectsPluginConfig
from netbox_custom_objects.group_views import CustomObjectTypeGroupListView
from netbox_custom_objects.models import CustomObjectTypeField
from .base import CustomObjectsTestCase


class CustomObjectTypeGroupListViewTest(CustomObjectsTestCase, TestCase):
    """Tests for the menu_name + group_name summary table."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.menu_name = "Security"
        cls.group_name = "Policies"
        cls.used_cot = cls.create_custom_object_type(
            name="used_policy",
            slug="used-policy",
            verbose_name="Used Policy",
            menu_name=cls.menu_name,
            group_name=cls.group_name,
        )
        CustomObjectTypeField.objects.create(
            custom_object_type=cls.used_cot,
            name="name",
            label="Name",
            type="text",
            primary=True,
            required=True,
        )
        cls.unused_cot = cls.create_custom_object_type(
            name="unused_policy",
            slug="unused-policy",
            verbose_name="Unused Policy",
            menu_name=cls.menu_name,
            group_name=cls.group_name,
        )
        cls.other_group_cot = cls.create_custom_object_type(
            name="OtherGroup",
            slug="other-group",
            menu_name=cls.menu_name,
            group_name="Objects",
        )

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            CustomObjectsPluginConfig,
            "should_skip_dynamic_model_creation",
            return_value=False,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        used_model = self.used_cot.get_model()
        used_model.objects.create(name="instance-1")
        used_model.objects.create(name="instance-2")

    def assertHttpStatus(self, response, expected_status):
        self.assertEqual(response.status_code, expected_status)

    def _group_list_url(self, **params):
        url = reverse(
            "plugins:netbox_custom_objects:customobjecttype_group_list",
            kwargs={"menu_name": self.menu_name, "group_name": self.group_name},
        )
        if params:
            query = "&".join(f"{key}={value}" for key, value in params.items())
            return f"{url}?{query}"
        return url

    def test_group_list_renders_standard_object_list_layout(self):
        """The group page uses the standard NetBox object list template and controls."""
        self.assertHttpStatus(self.client.get(self._group_list_url()), 200)
        response = self.client.get(self._group_list_url())
        content = response.content.decode()

        self.assertIn("quicksearch", content)
        self.assertIn("Configure table", content)
        self.assertIn("Used COT", content)
        self.assertIn("Unused COT", content)
        self.assertIn("Used Policy", content)
        self.assertIn("Export", content)

    def test_used_tab_shows_only_cots_with_instances(self):
        """Default Used tab lists COTs whose instance counter is greater than zero."""
        response = self.client.get(self._group_list_url())
        content = response.content.decode()

        self.assertIn("Used Policy", content)
        self.assertNotIn("Unused Policy", content)
        self.assertNotIn("used_policy", content)
        self.assertIn("2", content)

    def test_unused_tab_shows_only_cots_without_instances(self):
        """Unused tab lists COTs whose instance counter equals zero."""
        response = self.client.get(self._group_list_url(tab="unused"))
        content = response.content.decode()

        self.assertIn("Unused Policy", content)
        self.assertNotIn("Used Policy", content)

    def test_quick_search_filters_by_verbose_name(self):
        """Quick search narrows rows by COT verbose name."""
        response = self.client.get(self._group_list_url(q="Used"))
        content = response.content.decode()

        self.assertIn("Used Policy", content)
        self.assertNotIn("Unused Policy", content)

    def test_instance_count_survives_table_configure(self):
        """Instance counts must remain visible after NetBox table pagination/config."""
        request = RequestFactory().get(self._group_list_url())
        request.user = self.user
        view = CustomObjectTypeGroupListView()
        view.setup(request, menu_name=self.menu_name, group_name=self.group_name)
        view._instance_counts = {self.used_cot.pk: 2}
        rows = view.get_queryset(request)
        table = view.get_table(rows, request)
        counts = [row.get_cell("instance_count") for row in table.rows]
        self.assertEqual(counts, ["2"])
        """Each row name links to the COT's object list, not the type detail page."""
        response = self.client.get(self._group_list_url())
        content = response.content.decode()

        self.assertIn(f"/custom-objects/{self.used_cot.slug}/", content)

    def test_unknown_group_returns_404(self):
        """A menu/group pair with no matching COTs returns 404."""
        url = reverse(
            "plugins:netbox_custom_objects:customobjecttype_group_list",
            kwargs={"menu_name": self.menu_name, "group_name": "MissingGroup"},
        )
        self.assertHttpStatus(self.client.get(url), 404)

    def test_requires_view_permission(self):
        """Users without view permission cannot access the group list."""
        user = create_test_user("viewer", permissions=[])
        self.client.force_login(user)
        self.assertHttpStatus(self.client.get(self._group_list_url()), 403)
