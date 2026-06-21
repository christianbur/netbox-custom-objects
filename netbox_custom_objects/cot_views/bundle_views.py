"""Views for the Custom Objects → Bundles page (list + detail + enable/disable toggle)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import register_model_view

from netbox_custom_objects.cot_views.local_bundles import (
    discover_bundles,
    get_bundle_detail,
    get_bundles_path,
)
from netbox_custom_objects.models import Bundle

_RELOAD_HINT = _(
    "Enabling or disabling a bundle only takes full effect after the "
    "NetBox workers are restarted, because views, URLs and menus are registered "
    "at worker startup."
)


class BundleListView(LoginRequiredMixin, View):
    template_name = "netbox_custom_objects/bundles/list.html"

    def get(self, request):
        discovered = discover_bundles()
        states = {b.name: b for b in Bundle.objects.all()}
        rows = []
        for bundle in discovered:
            record = states.get(bundle["name"])
            # Ensure every discovered bundle has an activation record so its name
            # links to a stable detail URL (pk-based).  This is idempotent and
            # mirrors the lazy get_or_create the toggle view already performs.
            if record is None:
                record, _created = Bundle.objects.get_or_create(
                    name=bundle["name"],
                    defaults={"enabled": False},
                )
            rows.append(
                {
                    "name": bundle["name"],
                    "verbose_name": bundle["verbose_name"],
                    "package": bundle["package"],
                    "path": bundle["path"],
                    "enabled": bool(record.enabled),
                    "restart_required": bool(record.restart_required),
                    "last_error": record.last_error,
                    "detail_url": record.get_absolute_url(),
                }
            )
        return render(
            request,
            self.template_name,
            {
                "bundles": rows,
                "bundles_path": get_bundles_path(),
                "reload_hint": _RELOAD_HINT,
            },
        )


@register_model_view(Bundle)
class BundleView(LoginRequiredMixin, View):
    """Read-only detail page describing one discovered bundle.

    Shows the activation record's metadata together with the bundle's
    filesystem contents (manifest, provided COT views, bundled schema files),
    read live via the existing discovery helpers.  Performs no DB writes.
    """

    template_name = "netbox_custom_objects/bundle.html"

    def get(self, request, pk):
        instance = get_object_or_404(Bundle, pk=pk)
        detail = get_bundle_detail(instance.name)
        return render(
            request,
            self.template_name,
            {
                "object": instance,
                "detail": detail,
                "bundles_path": get_bundles_path(),
                "reload_hint": _RELOAD_HINT,
            },
        )


class BundleToggleView(LoginRequiredMixin, View):
    def post(self, request, name):
        record, _created = Bundle.objects.get_or_create(
            name=name,
            defaults={"enabled": False},
        )
        record.enabled = not record.enabled
        record.restart_required = True
        record.save(update_fields=["enabled", "restart_required", "last_updated"])
        verb = _("enabled") if record.enabled else _("disabled")
        messages.success(
            request,
            _("Bundle %(name)s %(verb)s. ") % {"name": name, "verb": verb}
            + str(_RELOAD_HINT),
        )
        return redirect(reverse("plugins:netbox_custom_objects:bundle_list"))
