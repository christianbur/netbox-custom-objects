"""Base class for COT views.

A COTView renders a related tab on a custom object's detail page.  Subclasses
set ``key``/``label``/``template_name`` and override ``get_context`` (and
optionally ``get_example_objects`` for an ephemeral, never-persisted preview).
"""

from django.http import HttpResponse
from django.shortcuts import render
from django.template import engines

# Base template every custom-object detail/tab page extends.
_CO_BASE_TEMPLATE = "netbox_custom_objects/customobject.html"

# Base template a proxy (collection) render extends — a standalone list-style
# page rather than a per-instance detail tab.
_CO_PROXY_BASE_TEMPLATE = "netbox_custom_objects/cot_proxy_base.html"


def normalize_query_params(params):
    """Normalise a ``related_object_filter`` mapping into ``filter()`` kwargs.

    NetBox ``query_params`` dicts often wrap scalar values in single-element
    lists (form-style).  Unwrap those so the values can be passed straight to
    ``QuerySet.filter(**kwargs)``.  A falsy/None input yields an empty dict.
    """
    if not params:
        return {}
    result = {}
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            value = value[0] if len(value) == 1 else list(value)
        result[key] = value
    return result


class COTView:
    # Unique registry key (also used in the tab URL: .../view/<key>/).
    key = ""
    # Tab label shown in the nav.
    label = ""
    # Template rendered for the tab body. It should extend ``base_template``.
    # Loader-resolved; leave blank to use ``template_string`` instead (handy for
    # self-contained bundles whose template dir isn't on the loader path).
    template_name = ""
    # Inline template source (used when ``template_name`` is blank). May
    # ``{% extends base_template %}`` since the parent is loader-resolvable.
    template_string = ""
    # Tab ordering weight (higher = further right).
    weight = 2100

    def get_template_string(self):
        return self.template_string

    def get_example_objects(self, cot):
        """Return ephemeral, in-memory example rows for ``cot``.

        These objects are never saved to the database; they exist only to give
        the view a minimal working example to render.
        """
        return []

    def get_context(self, request, cot, instance):
        """Build the template context for the tab body."""
        return {
            "object": instance,
            "cot": cot,
            "example_objects": self.get_example_objects(cot),
            "cot_view_key": self.key,
            "cot_view_label": self.label,
            "base_template": _CO_BASE_TEMPLATE,
        }

    def render(self, request, cot, instance):
        context = self.get_context(request, cot, instance)
        context.setdefault("base_template", _CO_BASE_TEMPLATE)
        # ``tab`` drives the active-tab highlight in customobject.html.
        context.setdefault("tab", f"cot_view_{self.key}")
        if self.template_name:
            return render(request, self.template_name, context)
        template = engines["django"].from_string(self.get_template_string())
        return HttpResponse(template.render(context, request))

    # ------------------------------------------------------------------
    # Proxy / collection mode
    #
    # A proxy COT (one that owns an ``object_proxy`` field) has no instances of
    # its own; its list page instead renders a live, read-only projection of
    # the field's target NetBox model.  These hooks are additive — the
    # per-instance ``render``/``get_context`` path above is untouched.
    # ------------------------------------------------------------------

    def get_proxy_queryset(self, request, cot, field):
        """Return the RBAC-restricted, filtered queryset for a proxy *field*.

        ``field.related_object_type`` names the target NetBox model;
        ``field.related_object_filter`` (a query_params dict) narrows it.
        Returns ``None`` if the target model can't be resolved.
        """
        model = field.related_object_type.model_class() if field.related_object_type_id else None
        if model is None:
            return None
        qs = model.objects.all()
        filters = normalize_query_params(field.related_object_filter)
        if filters:
            qs = qs.filter(**filters)
        # Honour object-level permissions when the manager supports it.
        if hasattr(qs, "restrict"):
            qs = qs.restrict(request.user, "view")
        return qs

    def get_proxy_context(self, request, cot, field):
        """Build the template context for a proxy (collection) render."""
        return {
            "cot": cot,
            "proxy_field": field,
            "object_list": self.get_proxy_queryset(request, cot, field),
            "example_objects": self.get_example_objects(cot),
            "cot_view_key": self.key,
            "cot_view_label": self.label,
            "base_template": _CO_PROXY_BASE_TEMPLATE,
        }

    def render_proxy(self, request, cot, field, extra_context=None):
        """Render this view in proxy mode for *cot*'s ``object_proxy`` *field*."""
        context = self.get_proxy_context(request, cot, field)
        return self._render_collection_response(request, context, extra_context)

    def get_collection_context(self, request, cot, queryset):
        """Build the template context for a collection render over real instances.

        Used when a (non-proxy) COT has an assigned view: the type's list page
        renders that view as its primary content, fed by the type's own
        RBAC-restricted instance queryset.
        """
        return {
            "cot": cot,
            "object_list": queryset,
            "example_objects": self.get_example_objects(cot),
            "cot_view_key": self.key,
            "cot_view_label": self.label,
            "base_template": _CO_PROXY_BASE_TEMPLATE,
        }

    def render_collection(self, request, cot, queryset, extra_context=None):
        """Render this view as the primary list-page content for *cot*."""
        context = self.get_collection_context(request, cot, queryset)
        return self._render_collection_response(request, context, extra_context)

    def _render_collection_response(self, request, context, extra_context=None):
        if extra_context:
            context.update(extra_context)
        context.setdefault("base_template", _CO_PROXY_BASE_TEMPLATE)
        if self.template_name:
            return render(request, self.template_name, context)
        template = engines["django"].from_string(self.get_template_string())
        return HttpResponse(template.render(context, request))
