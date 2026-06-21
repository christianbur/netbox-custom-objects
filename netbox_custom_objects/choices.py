from django.utils.translation import gettext_lazy as _
from extras.choices import CustomFieldTypeChoices
from utilities.choices import ChoiceSet


# Sentinel value for the plugin-only "Object Proxy" field type.  Kept as a
# module-level constant so callers don't have to repeat the literal string.
TYPE_OBJECT_PROXY = "object_proxy"


class CustomObjectFieldTypeChoices(ChoiceSet):
    """Field-type choices for Custom Object Type fields.

    A superset of NetBox core's ``CustomFieldTypeChoices`` plus the plugin-only
    ``object_proxy`` type.  Defined here (rather than mutating the core ChoiceSet
    in place) so the plugin's extra type never leaks into NetBox custom fields.
    """

    TYPE_OBJECT_PROXY = TYPE_OBJECT_PROXY

    CHOICES = tuple(CustomFieldTypeChoices.CHOICES) + (
        (TYPE_OBJECT_PROXY, _("Object Proxy")),
    )


class ObjectFieldOnDeleteChoices(ChoiceSet):
    """Controls what happens to a Custom Object when the referenced object is deleted."""
    CASCADE = "cascade"
    SET_NULL = "set_null"
    PROTECT = "protect"

    CHOICES = (
        (SET_NULL, _("Set null (clear the field, keep this object)")),
        (CASCADE, _("Cascade (delete this object too)")),
        (PROTECT, _("Protect (prevent deletion of the referenced object)")),
    )


class MappingFieldTypeChoices(ChoiceSet):
    CHAR = "char"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    OBJECT = "object"

    CHOICES = (
        (CHAR, _("String"), "cyan"),
        (INTEGER, _("Integer"), "orange"),
        (BOOLEAN, _("Boolean"), "green"),
        (DATE, _("Date"), "red"),
        (DATETIME, _("DateTime"), "blue"),
        (OBJECT, _("Object"), "orange"),
    )


#
# Search
#

class SearchWeightChoices(ChoiceSet):
    WEIGHT_NONE = 0
    WEIGHT_LOW = 1000
    WEIGHT_MEDIUM = 500
    WEIGHT_HIGH = 100

    CHOICES = (
        (WEIGHT_HIGH, _('High (100)')),
        (WEIGHT_MEDIUM, _('Medium (500)')),
        (WEIGHT_LOW, _('Low (1000)')),
        (WEIGHT_NONE, _('Not searchable')),
    )
