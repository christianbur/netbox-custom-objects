import logging

from django.apps import apps
from django.conf import settings
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from netbox.navigation import MenuGroup
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem
from packaging import version
from utilities.string import title

from netbox_custom_objects.constants import APP_LABEL

logger = logging.getLogger("netbox_custom_objects.navigation")

custom_object_type_plugin_menu_item = PluginMenuItem(
    link="plugins:netbox_custom_objects:customobjecttype_list",
    link_text=_("Custom Object Types"),
    buttons=(
        PluginMenuButton(
            "plugins:netbox_custom_objects:customobjecttype_add",
            _("Add"),
            "mdi mdi-plus-thick",
        ),
        PluginMenuButton(
            "plugins:netbox_custom_objects:customobjecttype_define",
            _("JSON import"),
            "mdi mdi-text-box-edit-outline",
        ),
    ),
    auth_required=True,
    permissions=['netbox_custom_objects.view_customobjecttype'],
)


def _cot_menu_name(custom_object_type):
    """Normalised ``menu_name`` of a CustomObjectType ("" when unset/unreadable)."""
    return (getattr(custom_object_type, "menu_name", "") or "").strip()


def uses_group_list_page(custom_object_type):
    """True when *custom_object_type* is listed via the group summary page."""
    return bool(_cot_menu_name(custom_object_type) and (custom_object_type.group_name or "").strip())


def _group_list_menu_item(menu_name, group_name):
    """Sidebar entry linking to the group summary page for *menu_name* / *group_name*."""
    menu_item = PluginMenuItem(
        link=None,
        link_text=group_name,
        auth_required=True,
        permissions=["netbox_custom_objects.view_customobjecttype"],
    )
    menu_item.url = reverse_lazy(
        "plugins:netbox_custom_objects:customobjecttype_group_list",
        kwargs={"menu_name": menu_name, "group_name": group_name},
    )
    return menu_item


class CustomObjectTypeMenuItems:
    group_name = ""
    menu_name = ""

    def __init__(self, group_name="", menu_name=""):
        self.group_name = group_name
        self.menu_name = menu_name

    def __iter__(self):
        CustomObjectType = apps.get_model(APP_LABEL, "CustomObjectType")
        for custom_object_type in CustomObjectType.objects.filter(group_name=self.group_name):
            # A COT lands in exactly one menu: the stock Custom Objects menu
            # (menu_name == "") or its named top-level menu.
            if _cot_menu_name(custom_object_type) != self.menu_name:
                continue
            # menu_name + group_name → group summary page, not individual entries.
            if uses_group_list_page(custom_object_type):
                continue
            model = custom_object_type.get_model()
            # Proxy types hold no instances of their own — suppress the
            # Add/Import buttons (the menu entry still links to the list page,
            # which renders the proxy view).
            if custom_object_type.is_proxy():
                buttons = ()
            else:
                add_button = PluginMenuButton(
                    None,
                    _("Add"),
                    "mdi mdi-plus-thick",
                )
                add_button.url = reverse_lazy(
                    f"plugins:{APP_LABEL}:customobject_add",
                    kwargs={
                        "custom_object_type": custom_object_type.slug
                    },
                )
                bulk_import_button = PluginMenuButton(
                    None,
                    _('Import'),
                    'mdi mdi-upload'
                )
                bulk_import_button.url = reverse_lazy(
                    f"plugins:{APP_LABEL}:customobject_bulk_import",
                    kwargs={
                        "custom_object_type": custom_object_type.slug
                    },
                )
                buttons = (add_button, bulk_import_button)
            menu_item = PluginMenuItem(
                link=None,
                link_text=_(title(model._meta.verbose_name_plural)),
                buttons=buttons,
                auth_required=True,
                permissions=[f'netbox_custom_objects.view_{model._meta.model_name}'],
            )
            menu_item.url = reverse_lazy(
                f"plugins:{APP_LABEL}:customobject_list",
                kwargs={"custom_object_type": custom_object_type.slug},
            )
            yield menu_item


current_version = version.parse(settings.RELEASE.version)


def get_grouped_menu_items():
    app_config = apps.get_app_config("netbox_custom_objects")
    if app_config.should_skip_dynamic_model_creation():
        return []
    CustomObjectType = apps.get_model(APP_LABEL, "CustomObjectType")
    groups = []
    # Only build a group header for group_names that still have at least one COT
    # WITHOUT a menu_name, so a fully-relocated group disappears from the stock menu.
    group_names = sorted({
        cot.group_name
        for cot in CustomObjectType.objects.exclude(group_name="")
        if not _cot_menu_name(cot)
    })
    for group_name in group_names:
        groups.append((group_name, CustomObjectTypeMenuItems(group_name=group_name)))
    return groups


bundles_menu_item = PluginMenuItem(
    link="plugins:netbox_custom_objects:bundle_list",
    link_text=_("Bundles"),
    auth_required=True,
)


def get_groups():
    return [
        (_("Config"), (custom_object_type_plugin_menu_item, bundles_menu_item)),
    ] + get_grouped_menu_items() + [
        (_("Objects"), CustomObjectTypeMenuItems())
    ]


# ---------------------------------------------------------------------------
# Per-menu-name top-level menus
#
# A CustomObjectType with a non-empty ``menu_name`` is removed from the stock
# Custom Objects menu (above) and listed under its own top-level navigation menu
# titled by the ``menu_name``; types sharing a ``menu_name`` collect under one
# menu, still grouped internally by ``group_name``.  NetBox snapshots the set of
# top-level menus at startup, so ``register_menu_name_menus`` runs once in
# ``ready()``; the menu CONTENTS are computed live per request (a COT moving
# between existing menu_names shows up without a restart, but a brand-new
# menu_name needs one — mirroring how a brand-new group_name behaves).
# ---------------------------------------------------------------------------

# Icon for the generated top-level menus (matches the stock Custom Objects menu).
_MENU_NAME_ICON = "mdi mdi-toy-brick-outline"


def _distinct_menu_names():
    """Sorted list of distinct, non-empty ``menu_name`` values across all COTs."""
    CustomObjectType = apps.get_model(APP_LABEL, "CustomObjectType")
    names = (
        CustomObjectType.objects
        .exclude(menu_name="")
        .values_list("menu_name", flat=True)
        .distinct()
    )
    return sorted({(n or "").strip() for n in names if (n or "").strip()})


def _menu_name_groups(menu_name):
    """``[(group_label, items)]`` for one top-level ``menu_name`` menu.

    When both ``menu_name`` and ``group_name`` are set, ``group_name`` becomes a
    single sidebar link to the group summary page (not a submenu of COT entries).
    COTs with ``menu_name`` but no ``group_name`` fall under an "Objects" group.
    """
    CustomObjectType = apps.get_model(APP_LABEL, "CustomObjectType")
    cots = [c for c in CustomObjectType.objects.all() if _cot_menu_name(c) == menu_name]
    groups = []
    group_names = sorted({c.group_name for c in cots if c.group_name})
    ungrouped_items = []
    if any(not c.group_name for c in cots):
        ungrouped_items = list(CustomObjectTypeMenuItems(group_name="", menu_name=menu_name))
    if group_names or ungrouped_items:
        group_links = [_group_list_menu_item(menu_name, group_name) for group_name in group_names]
        groups.append((_("Objects"), group_links + ungrouped_items))
    return groups


def _make_menu_name_menu(menu_name):
    """Build a top-level ``PluginMenu`` for ``menu_name`` whose groups update live."""

    class _MenuNameMenu(PluginMenu):
        icon_class = _MENU_NAME_ICON

        def __init__(self, label):
            self.label = label

        @property
        def groups(self):
            try:
                return [MenuGroup(label, items) for label, items in _menu_name_groups(self.label)]
            except Exception:
                logger.exception("failed building groups for menu_name menu %r", self.label)
                return []

    return _MenuNameMenu(menu_name)


def register_menu_name_menus():
    """Register one top-level menu per distinct ``menu_name`` (idempotent).

    Called from ``CustomObjectsPluginConfig.ready()`` after the stock menu has
    been registered.  Skips DB access (and registration) when dynamic models
    aren't available yet; registration is retried on the next process start.
    """
    from django.db.utils import OperationalError, ProgrammingError
    from netbox.registry import registry

    app_config = apps.get_app_config("netbox_custom_objects")
    if app_config.should_skip_dynamic_model_creation():
        return

    try:
        menu_names = _distinct_menu_names()
    except (OperationalError, ProgrammingError):
        logger.warning("database unavailable — per-menu-name menus not registered until next start")
        return

    existing_labels = {getattr(m, "label", None) for m in registry["plugins"]["menus"]}
    for menu_name in menu_names:
        if menu_name in existing_labels:
            continue
        registry["plugins"]["menus"].append(_make_menu_name_menu(menu_name))
        logger.debug("registered top-level menu %r", menu_name)


class _DynamicPluginMenu(PluginMenu):
    def __init__(self, label, groups_fn, icon_class=None):
        self.label = label
        self._groups_fn = groups_fn
        if icon_class is not None:
            self.icon_class = icon_class

    @property
    def groups(self):
        return [MenuGroup(label, items) for label, items in self._groups_fn()]


menu = _DynamicPluginMenu(
    label=_("Custom Objects"),
    groups_fn=get_groups,
    icon_class="mdi mdi-toy-brick-outline",
)
