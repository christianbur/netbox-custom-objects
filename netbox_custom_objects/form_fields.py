import json

import yaml
from django import forms
from django.utils.translation import gettext_lazy as _
from utilities.forms.fields import JSONField


class JSONOrYAMLField(JSONField):
    """
    Accept structured data as JSON or YAML text; store as a Python object.

    Extends NetBox's :class:`~utilities.forms.fields.JSONField` so edit forms
    accept either format while the model continues to use ``JSONField``.
    """

    def __init__(self, *args, require_mapping=False, **kwargs):
        self.require_mapping = require_mapping
        if 'help_text' not in kwargs:
            kwargs['help_text'] = _(
                'Enter structured data in <a href="https://json.org/">JSON</a> '
                'or <a href="https://yaml.org/">YAML</a> format.'
            )
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if not isinstance(value, str):
            if self.require_mapping and value is not None and not isinstance(value, dict):
                raise forms.ValidationError(_('Expected a mapping (JSON object / YAML mapping).'))
            return value

        value = value.strip()
        if not value:
            return None

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            try:
                parsed = yaml.safe_load(value)
            except yaml.YAMLError as exc:
                raise forms.ValidationError(_('Invalid JSON or YAML data: %(error)s') % {'error': exc}) from exc

        if self.require_mapping and parsed is not None and not isinstance(parsed, dict):
            raise forms.ValidationError(_('Expected a mapping (JSON object / YAML mapping).'))

        return parsed
