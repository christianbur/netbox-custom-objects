"""
Tests for the portable-schema UI tabs/screens:

- ``CustomObjectTypeSchemaView`` — the read-only "Export" tab on the COT detail
  page, which renders the COT's portable-schema export as text (YAML + JSON).
- ``CustomObjectTypeDefineView`` — the "Define via text" screen, which parses,
  validates and applies a pasted portable-schema document via the existing
  executor.

These views build on the portable-schema backend (exporter / comparator /
executor / validation); the tests assert the UI wiring, not the schema logic
itself (covered by tests/schema/).
"""
import json

from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from netbox_custom_objects.models import CustomObjectType, CustomObjectTypeField

from .base import CustomObjectsTestCase, TransactionCleanupMixin


def _new_cot_document(slug="gadget", name="gadget"):
    """A minimal, valid single-COT schema document for a brand-new COT."""
    return {
        "schema_version": "1",
        "types": [
            {
                "name": name,
                "slug": slug,
                "description": "A gadget",
                "fields": [
                    {"id": 1, "name": "label", "type": "text", "primary": True},
                    {"id": 2, "name": "quantity", "type": "integer"},
                ],
            }
        ],
    }


class _SuperuserMixin:
    """Elevate the base test user to a superuser so add/change perms pass."""

    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)


# ===========================================================================
# Export tab
# ===========================================================================

class SchemaExportTabTestCase(_SuperuserMixin, CustomObjectsTestCase, TestCase):
    """The Export tab renders the COT's portable-schema document as text."""

    @classmethod
    def setUpTestData(cls):
        cls.cot = cls.create_custom_object_type(
            name="widget",
            slug="widget",
            description="A widget",
            menu_name="Inventory",
            link_table=True,
            metadata="owner: net-team\ntier: gold\n",
        )
        cls.field = cls.create_custom_object_type_field(
            cls.cot, name="label", type="text", primary=True,
        )

    def _url(self):
        return reverse(
            "plugins:netbox_custom_objects:customobjecttype_export",
            kwargs={"pk": self.cot.pk},
        )

    def test_export_tab_renders_document_text(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Identity + the three enhancement attributes round-trip into the text.
        self.assertIn("widget", content)
        self.assertIn("Inventory", content)        # menu_name
        self.assertIn("owner: net-team", content)  # metadata (verbatim)
        self.assertIn("label", content)            # field name
        # Both JSON and YAML renderings are offered.
        self.assertIn("cot-export-json-text", content)
        self.assertIn("cot-export-yaml-text", content)

    def test_export_tab_json_is_valid_and_complete(self):
        response = self.client.get(self._url())
        document = response.context["schema_json"]
        parsed = json.loads(document)
        self.assertEqual(parsed["schema_version"], "1")
        self.assertEqual(len(parsed["types"]), 1)
        type_def = parsed["types"][0]
        self.assertEqual(type_def["slug"], "widget")
        self.assertTrue(type_def["link_table"])
        self.assertEqual(type_def["menu_name"], "Inventory")
        self.assertIn("owner: net-team", type_def["metadata"])
        self.assertEqual(type_def["fields"][0]["name"], "label")


# ===========================================================================
# Define via text — read-only paths (GET / preview / validation)
# ===========================================================================

class SchemaDefineReadOnlyTestCase(_SuperuserMixin, CustomObjectsTestCase, TestCase):
    """GET, preview and validation-error paths make no DB changes."""

    def _url(self):
        return reverse("plugins:netbox_custom_objects:customobjecttype_define")

    def test_get_renders_form(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("JSON import", response.content.decode())

    def test_preview_valid_document_shows_diff_without_applying(self):
        document = json.dumps(_new_cot_document())
        response = self.client.post(
            self._url(), {"document_text": document, "action": "preview"}
        )
        self.assertEqual(response.status_code, 200)
        diffs = response.context["diffs"]
        self.assertIsNotNone(diffs)
        self.assertEqual(len(diffs), 1)
        self.assertTrue(diffs[0].is_new)
        self.assertEqual(diffs[0].slug, "gadget")
        # Preview must not create anything.
        self.assertFalse(CustomObjectType.objects.filter(slug="gadget").exists())

    def test_invalid_document_reports_schema_errors(self):
        # Missing required top-level "schema_version" key.
        bad = json.dumps({"types": _new_cot_document()["types"]})
        response = self.client.post(
            self._url(), {"document_text": bad, "action": "apply"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["schema_errors"])
        self.assertFalse(CustomObjectType.objects.filter(slug="gadget").exists())

    def test_unparseable_text_reports_parse_error(self):
        response = self.client.post(
            self._url(), {"document_text": "{not valid json or yaml: [", "action": "preview"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["parse_error"])


# ===========================================================================
# Define via text — apply (creates COTs; needs TransactionTestCase for DDL)
# ===========================================================================

class SchemaDefineApplyTestCase(
    _SuperuserMixin, TransactionCleanupMixin, CustomObjectsTestCase, TransactionTestCase
):
    """Applying a pasted document creates the COT(s) via the executor."""

    def _url(self):
        return reverse("plugins:netbox_custom_objects:customobjecttype_define")

    def test_apply_creates_custom_object_type(self):
        document = json.dumps(_new_cot_document())
        response = self.client.post(
            self._url(), {"document_text": document, "action": "apply"}
        )
        # Successful apply redirects back to the list view.
        self.assertEqual(response.status_code, 302)
        cot = CustomObjectType.objects.get(slug="gadget")
        field_names = set(
            CustomObjectTypeField.objects.filter(custom_object_type=cot)
            .values_list("name", flat=True)
        )
        self.assertEqual(field_names, {"label", "quantity"})

    def test_apply_accepts_yaml(self):
        import yaml

        document = yaml.safe_dump(_new_cot_document(slug="sprocket", name="sprocket"))
        response = self.client.post(
            self._url(), {"document_text": document, "action": "apply"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CustomObjectType.objects.filter(slug="sprocket").exists())
