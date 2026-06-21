"""Tests for COT bundle discovery, activation records and startup loading."""

import builtins
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.test import TestCase

from netbox_custom_objects.cot_views.local_bundles import (
    load_enabled_bundles,
    prefix_schema_document,
)
from netbox_custom_objects.models import Bundle

_REAL_IMPORT = builtins.__import__


@contextmanager
def _allow_bundle_loading():
    from django.apps import apps

    app_config = apps.get_app_config("netbox_custom_objects")

    def import_side_effect(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"enabled_pkg", "disabled_pkg"}:
            return MagicMock()
        return _REAL_IMPORT(name, globals, locals, fromlist, level)

    with patch.object(
        app_config, "should_skip_dynamic_model_creation", return_value=False
    ):
        with patch("builtins.__import__", side_effect=import_side_effect):
            yield


class BundleActivationTestCase(TestCase):
    def test_prefix_schema_document_adds_package_to_names_slugs_views_and_refs(self):
        doc = {
            "schema_version": "1",
            "types": [
                {
                    "name": "action",
                    "slug": "action",
                    "views": "rulebook",
                    "fields": [
                        {
                            "name": "parent",
                            "type": "object",
                            "related_object_type": "custom-objects/zone",
                        }
                    ],
                },
                {
                    "name": "zone",
                    "slug": "zone",
                },
                {
                    "name": "rulebook",
                    "slug": "rulebook",
                    "fields": [
                        {
                            "name": "act",
                            "type": "object",
                            "related_object_type": "custom-objects/action",
                        }
                    ],
                },
            ],
        }
        prefixed = prefix_schema_document(doc, "security")
        self.assertEqual(prefixed["types"][0]["name"], "security_action")
        self.assertEqual(prefixed["types"][0]["slug"], "security-action")
        self.assertEqual(prefixed["types"][0]["views"], "security_rulebook")
        self.assertEqual(
            prefixed["types"][2]["fields"][0]["related_object_type"],
            "custom-objects/security-action",
        )
        self.assertEqual(prefixed["types"][0]["fields"][0]["related_object_type"], "custom-objects/security-zone")

    def test_prefix_schema_document_is_idempotent(self):
        doc = {"types": [{"name": "security_action", "slug": "security-action"}]}
        once = prefix_schema_document(doc, "security")
        twice = prefix_schema_document(once, "security")
        self.assertEqual(once, twice)

    def test_new_bundle_record_defaults_to_disabled(self):
        record = Bundle.objects.create(name="test_bundle")
        self.assertFalse(record.enabled)

    def test_get_or_create_does_not_enable_existing_disabled_record(self):
        Bundle.objects.create(name="test_bundle", enabled=False)
        record, created = Bundle.objects.get_or_create(
            name="test_bundle",
            defaults={"enabled": False},
        )
        self.assertFalse(created)
        self.assertFalse(record.enabled)

    @patch("netbox_custom_objects.cot_views.local_bundles._apply_bundle_schema")
    @patch("netbox_custom_objects.cot_views.local_bundles.discover_bundles")
    def test_load_enabled_bundles_skips_disabled_records(
        self, mock_discover, mock_apply
    ):
        Bundle.objects.create(name="enabled_bundle", enabled=True)
        Bundle.objects.create(name="disabled_bundle", enabled=False)
        mock_discover.return_value = [
            {"name": "enabled_bundle", "package": "enabled_pkg", "path": "/tmp/enabled"},
            {"name": "disabled_bundle", "package": "disabled_pkg", "path": "/tmp/disabled"},
        ]

        with _allow_bundle_loading():
            load_enabled_bundles()

        mock_apply.assert_called_once()
        self.assertEqual(
            mock_apply.call_args[0][0]["name"],
            "enabled_bundle",
        )

    @patch("netbox_custom_objects.cot_views.local_bundles._apply_bundle_schema")
    @patch("netbox_custom_objects.cot_views.local_bundles.discover_bundles")
    def test_load_enabled_bundles_noops_when_none_enabled(
        self, mock_discover, mock_apply
    ):
        Bundle.objects.create(name="disabled_bundle", enabled=False)
        mock_discover.return_value = [
            {"name": "disabled_bundle", "package": "disabled_pkg", "path": "/tmp/disabled"},
        ]

        with _allow_bundle_loading():
            load_enabled_bundles()

        mock_apply.assert_not_called()

    @patch("netbox_custom_objects.cot_views.local_bundles._clear_bundle_restart_flags")
    @patch("netbox_custom_objects.cot_views.local_bundles._apply_bundle_schema")
    @patch("netbox_custom_objects.cot_views.local_bundles.discover_bundles")
    def test_load_enabled_bundles_clears_restart_flags(
        self, mock_discover, mock_apply, mock_clear
    ):
        Bundle.objects.create(name="enabled_bundle", enabled=True, restart_required=True)
        mock_discover.return_value = [
            {"name": "enabled_bundle", "package": "enabled_pkg", "path": "/tmp/enabled"},
        ]

        with _allow_bundle_loading():
            load_enabled_bundles()

        mock_clear.assert_called_once()

    @patch("netbox_custom_objects.cot_views.local_bundles._clear_bundle_restart_flags")
    @patch("netbox_custom_objects.cot_views.local_bundles.discover_bundles")
    def test_load_enabled_bundles_clears_restart_flags_when_none_enabled(
        self, mock_discover, mock_clear
    ):
        Bundle.objects.create(name="disabled_bundle", enabled=False, restart_required=True)
        mock_discover.return_value = []

        with _allow_bundle_loading():
            load_enabled_bundles()

        mock_clear.assert_called_once()
