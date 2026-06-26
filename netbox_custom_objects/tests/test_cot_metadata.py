"""Tests for the CustomObjectType ``metadata`` attribute."""

from django.test import Client, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from core.models import ObjectType
from users.models import ObjectPermission
from utilities.testing import create_test_user

from netbox_custom_objects.form_fields import JSONOrYAMLField
from netbox_custom_objects.forms import CustomObjectTypeForm
from netbox_custom_objects.models import CustomObjectType
from netbox_custom_objects.schema.executor import apply_document
from netbox_custom_objects.schema.exporter import export_cot
from netbox_custom_objects.schema.format import SCHEMA_FORMAT_VERSION

from .base import CustomObjectsTestCase, create_token


class JSONOrYAMLFieldTestCase(TestCase):
    def setUp(self):
        self.field = JSONOrYAMLField(require_mapping=True)

    def test_parses_json_object(self):
        self.assertEqual(self.field.to_python('{"a": 1}'), {'a': 1})

    def test_parses_yaml_mapping(self):
        self.assertEqual(
            self.field.to_python('panel: security\nversion: 1\n'),
            {'panel': 'security', 'version': 1},
        )

    def test_rejects_non_mapping_yaml(self):
        with self.assertRaises(Exception):
            self.field.to_python('- item\n- other\n')

    def test_empty_string_becomes_none(self):
        self.assertIsNone(self.field.to_python(''))


class CustomObjectTypeMetadataFormTestCase(CustomObjectsTestCase, TestCase):
    def test_form_accepts_yaml_metadata(self):
        form = CustomObjectTypeForm(
            data={
                'name': 'yaml_meta',
                'slug': 'yaml-meta',
                'metadata': 'panel: security\nenabled: true\n',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['metadata'], {'panel': 'security', 'enabled': True})

    def test_form_accepts_json_metadata(self):
        form = CustomObjectTypeForm(
            data={
                'name': 'json_meta',
                'slug': 'json-meta',
                'metadata': '{"panel": "security", "enabled": true}',
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['metadata'], {'panel': 'security', 'enabled': True})


class CustomObjectTypeMetadataViewTestCase(CustomObjectsTestCase, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_user(
            'metadata-view-user',
            permissions=[
                'netbox_custom_objects.view_customobjecttype',
                'netbox_custom_objects.change_customobjecttype',
            ],
        )
        cls.cot = cls.create_custom_object_type(
            name='view_metadata_cot',
            slug='view-metadata-cot',
            metadata={'panel': 'security'},
        )
        cot_object_type = ObjectType.objects.get_for_model(CustomObjectType)
        for action in ('view', 'change'):
            obj_perm = ObjectPermission(name=f'metadata-view-{action}', actions=[action])
            obj_perm.save()
            obj_perm.users.add(cls.user)
            obj_perm.object_types.add(cot_object_type)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_detail_view_shows_metadata_and_comments_panels(self):
        url = reverse('plugins:netbox_custom_objects:customobjecttype', kwargs={'pk': self.cot.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>Metadata</h2>')
        self.assertContains(response, 'panel: security')
        self.assertContains(response, '>Comments</h2>')

    def test_edit_view_shows_metadata_and_comments_without_duplication(self):
        url = reverse('plugins:netbox_custom_objects:customobjecttype_edit', kwargs={'pk': self.cot.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(content.count('name="metadata"'), 1)
        self.assertEqual(content.count('name="comments"'), 1)
        self.assertContains(response, 'Metadata')
        self.assertNotContains(response, 'Comments &amp; Metadata')
        self.assertNotContains(response, '>Metadata</h2>')

    def test_edit_view_persists_yaml_metadata(self):
        url = reverse('plugins:netbox_custom_objects:customobjecttype_edit', kwargs={'pk': self.cot.pk})
        response = self.client.post(
            url,
            data={
                'name': self.cot.name,
                'slug': self.cot.slug,
                'metadata': 'owner: network-team\nversion: 2\n',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.cot.refresh_from_db()
        self.assertEqual(self.cot.metadata, {'owner': 'network-team', 'version': 2})


class CustomObjectTypeMetadataFieldTestCase(CustomObjectsTestCase, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cot = cls.create_custom_object_type(
            name='metadata_cot',
            slug='metadata-cot',
            metadata={'panel': 'security', 'version': 1},
        )

    def test_metadata_persisted_on_model(self):
        self.cot.refresh_from_db()
        self.assertEqual(self.cot.metadata, {'panel': 'security', 'version': 1})

    def test_metadata_exported_in_portable_schema(self):
        exported = export_cot(self.cot)
        self.assertEqual(
            exported['metadata'],
            {'panel': 'security', 'version': 1},
        )

    def test_metadata_omitted_from_export_when_unset(self):
        bare = self.create_custom_object_type(name='bare_metadata', slug='bare-metadata')
        exported = export_cot(bare)
        self.assertNotIn('metadata', exported)

    def test_metadata_roundtrip_via_portable_schema(self):
        document = {
            'schema_version': SCHEMA_FORMAT_VERSION,
            'types': [
                {
                    'name': 'schema_metadata_cot',
                    'slug': 'schema-metadata-cot',
                    'metadata': {'source': 'yaml', 'enabled': True},
                    'fields': [
                        {
                            'id': 1,
                            'name': 'name',
                            'type': 'text',
                            'primary': True,
                        },
                    ],
                },
            ],
        }
        apply_document(document)
        cot = CustomObjectType.objects.get(slug='schema-metadata-cot')
        self.assertEqual(cot.metadata, {'source': 'yaml', 'enabled': True})


class CustomObjectTypeMetadataAPITestCase(CustomObjectsTestCase, TestCase):
    def setUp(self):
        self.user = create_test_user('metadata-api-user')
        token_key = create_token(self.user)
        self.header = {'HTTP_AUTHORIZATION': f'Token {token_key}'}
        self.client = APIClient()

        for action in ('view', 'add', 'change'):
            obj_perm = ObjectPermission(name=f'metadata-{action}', actions=[action])
            obj_perm.save()
            obj_perm.users.add(self.user)
            obj_perm.object_types.add(ObjectType.objects.get_for_model(CustomObjectType))

    def test_metadata_in_detail_response(self):
        cot = CustomObjectType.objects.create(
            name='api_metadata',
            slug='api-metadata',
            metadata={'key': 'value'},
        )
        url = reverse(
            'plugins-api:netbox_custom_objects-api:customobjecttype-detail',
            kwargs={'pk': cot.pk},
        )
        response = self.client.get(url, **self.header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['metadata'], {'key': 'value'})

    def test_metadata_writable_on_create_and_update(self):
        url = reverse('plugins-api:netbox_custom_objects-api:customobjecttype-list')
        response = self.client.post(
            url,
            {
                'name': 'created_metadata',
                'slug': 'created-metadata',
                'metadata': {'created': True},
            },
            format='json',
            **self.header,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['metadata'], {'created': True})

        detail_url = reverse(
            'plugins-api:netbox_custom_objects-api:customobjecttype-detail',
            kwargs={'pk': response.data['id']},
        )
        patch_response = self.client.patch(
            detail_url,
            {'metadata': {'updated': True}},
            format='json',
            **self.header,
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data['metadata'], {'updated': True})
