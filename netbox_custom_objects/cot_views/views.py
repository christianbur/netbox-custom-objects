"""Request-time dispatcher that renders a selected COT view as a related tab.

A single, COT-agnostic URL (registered statically in ``urls.py``) serves every
type and every registered view: the view key is resolved against the registry
at request time, so a brand-new local-plugin view needs no per-view URL — only
a worker restart to populate the registry.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views import View

from utilities.views import ConditionalLoginRequiredMixin

from netbox_custom_objects.cot_views.registry import get_cot_view
from netbox_custom_objects.models import CustomObjectType


class CustomObjectCOTView(ConditionalLoginRequiredMixin, View):
    def get(self, request, custom_object_type, pk, view_key, **kwargs):
        cot = get_object_or_404(CustomObjectType, slug=custom_object_type)

        # The binding is dynamic and DB-backed: the view must be selected on the
        # type AND present in the registry.
        if view_key not in cot.get_view_keys():
            raise Http404("View not enabled for this Custom Object Type.")
        view_cls = get_cot_view(view_key)
        if view_cls is None:
            raise Http404("Unknown COT view.")

        model = cot.get_model()
        qs = model.objects.all()
        if hasattr(qs, "restrict"):
            qs = qs.restrict(request.user, "view")
        instance = get_object_or_404(qs, pk=pk)

        return view_cls().render(request, cot, instance)
