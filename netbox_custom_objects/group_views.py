"""List views for CustomObjectType groups (menu_name + group_name)."""

from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.object_actions import BulkExport
from netbox.views import generic
from utilities.permissions import get_permission_for_model

from netbox_custom_objects import filtersets, forms, tables
from netbox_custom_objects.models import CustomObjectType
from netbox_custom_objects.navigation import _cot_menu_name, uses_group_list_page

TAB_USED = "used"
TAB_UNUSED = "unused"
VALID_TABS = {TAB_USED, TAB_UNUSED}


def _cot_instance_count(custom_object_type, user):
    """Return the number of instances for *custom_object_type* visible to *user*."""
    if custom_object_type.is_proxy():
        return 0
    model = custom_object_type.get_model()
    queryset = model.objects.all()
    if hasattr(queryset, "restrict"):
        queryset = queryset.restrict(user, "view")
    return queryset.count()


def _group_cots(menu_name, group_name):
    """COTs in *group_name* under *menu_name* that use the group list page."""
    return [
        cot
        for cot in CustomObjectType.objects.filter(group_name=group_name)
        if _cot_menu_name(cot) == menu_name and uses_group_list_page(cot)
    ]


class CustomObjectTypeGroupListView(generic.ObjectListView):
    """Standard NetBox table of COTs sharing a menu_name + group_name with instance counts."""

    queryset = CustomObjectType.objects.all()
    table = tables.CustomObjectTypeGroupListTable
    filterset = filtersets.CustomObjectTypeGroupListFilterSet
    filterset_form = forms.CustomObjectTypeGroupListFilterForm
    template_name = "netbox_custom_objects/customobjecttype_group_list.html"
    actions = (BulkExport,)

    def setup(self, request, *args, **kwargs):
        self.menu_name = kwargs.get("menu_name", "")
        self.group_name = kwargs.get("group_name", "")
        self._instance_counts = {}
        self._active_tab = request.GET.get("tab", TAB_USED)
        if self._active_tab not in VALID_TABS:
            self._active_tab = TAB_USED
        if not _group_cots(self.menu_name, self.group_name):
            raise Http404
        self._compute_instance_counts(request)
        super().setup(request, *args, **kwargs)

    def _compute_instance_counts(self, request):
        """Populate ``_instance_counts`` for every COT in the group the user may view."""
        for cot in _group_cots(self.menu_name, self.group_name):
            model = cot.get_model()
            perm = get_permission_for_model(model, "view")
            if not request.user.has_perm(perm):
                continue
            self._instance_counts[cot.pk] = _cot_instance_count(cot, request.user)

    def get_queryset(self, request):
        pks = []
        for cot_pk, count in self._instance_counts.items():
            if self._active_tab == TAB_USED and count == 0:
                continue
            if self._active_tab == TAB_UNUSED and count > 0:
                continue
            pks.append(cot_pk)
        return CustomObjectType.objects.filter(pk__in=pks).order_by("name")

    def get_table(self, data, request, bulk_actions=True):
        # Materialize before configure() re-evaluates the queryset (which would
        # drop dynamically assigned attributes like instance_count).
        rows = list(data)
        for cot in rows:
            cot.instance_count = self._instance_counts.get(cot.pk, 0)
        return super().get_table(rows, request, bulk_actions)

    def get(self, request, menu_name, group_name):
        return super().get(request)

    def get_extra_context(self, request):
        base_url = reverse(
            "plugins:netbox_custom_objects:customobjecttype_group_list",
            kwargs={"menu_name": self.menu_name, "group_name": self.group_name},
        )
        used_count = sum(1 for count in self._instance_counts.values() if count > 0)
        unused_count = sum(1 for count in self._instance_counts.values() if count == 0)
        query_suffix = ""
        if request.GET:
            params = request.GET.copy()
            params.pop("tab", None)
            if params:
                query_suffix = f"&{params.urlencode()}"

        return {
            "menu_name": self.menu_name,
            "group_name": self.group_name,
            "group_tabs": [
                {
                    "label": _("Used COT"),
                    "url": f"{base_url}?tab={TAB_USED}{query_suffix}",
                    "active": self._active_tab == TAB_USED,
                    "count": used_count,
                },
                {
                    "label": _("Unused COT"),
                    "url": f"{base_url}?tab={TAB_UNUSED}{query_suffix}",
                    "active": self._active_tab == TAB_UNUSED,
                    "count": unused_count,
                },
            ],
        }
