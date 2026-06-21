import logging

from netbox_custom_objects.constants import APP_LABEL

from .views.combined import (
    COMBINED_LABEL,
    COMBINED_WEIGHT,
    _distinct_menu_names,
    _menu_tab_slug,
    make_co_combined_view,
    make_co_menu_view,
    register_combined_tabs,
    register_menu_name_tabs,
)

logger = logging.getLogger('netbox_custom_objects.related_tabs')

# Action name / path / URL name for the combined tab on custom-object host pages.
# Kept in sync with the {% custom_objects_tab_link %} <li> in customobject.html
# and the custom_objects_tab_link template tag.
_CO_COMBINED_ACTION = 'custom_objects'
_CO_COMBINED_PATH = 'custom-objects'
# CustomObject._get_viewname('custom_objects') ->
# 'plugins:netbox_custom_objects:customobject_custom_objects'
CO_COMBINED_URL_NAME = f'customobject_{_CO_COMBINED_ACTION}'


def _inject_co_urls():
    """
    Inject the generic combined-tab URL for custom-object host pages into
    ``netbox_custom_objects.urls``.

    Custom-object detail pages are served by one generic view and never call
    ``get_model_urls()``, so the tab view has no URL pattern. Add ONE slug-agnostic
    route (``<str:custom_object_type>/<int:pk>/custom-objects/``) at ready() time,
    before the URLconf freezes — it reverses for any slug, including COTs created
    after startup. The URL name follows CustomObject._get_viewname():
    ``plugins:netbox_custom_objects:customobject_custom_objects``.
    """
    try:
        import netbox_custom_objects.urls as co_urls
        from django.urls import path as url_path
    except ImportError:
        return

    existing_names = {p.name for p in co_urls.urlpatterns if hasattr(p, 'name') and p.name}
    if CO_COMBINED_URL_NAME in existing_names:
        return

    full_path = f'<str:custom_object_type>/<int:pk>/{_CO_COMBINED_PATH}/'
    co_urls.urlpatterns.append(
        url_path(full_path, make_co_combined_view().as_view(), name=CO_COMBINED_URL_NAME)
    )
    logger.debug("injected URL pattern '%s'", CO_COMBINED_URL_NAME)


def _co_menu_url_name(menu_name):
    """URL name for a per-menu-name tab on custom-object host pages.

    Mirrors ``CustomObject._get_viewname('custom_objects_menu_<slug>')`` so the
    ``custom_objects_menu_tab_links`` template tag can reverse it via
    ``get_action_url(instance, action='custom_objects_menu_<slug>')``.
    """
    slug = _menu_tab_slug(menu_name).replace('-', '_')
    return f'customobject_custom_objects_menu_{slug}'


def _inject_co_menu_urls():
    """
    Inject one slug-agnostic per-menu-name tab URL for custom-object host pages
    per distinct ``menu_name``.

    Custom-object detail pages are served by one generic view and never call
    ``get_model_urls()``, so the per-menu tab (the CO→CO analogue of the built-in
    ``register_menu_name_tabs`` tabs) has no URL pattern.  Add ONE COT-agnostic
    route per distinct ``menu_name`` (``<str:custom_object_type>/<int:pk>/
    custom-objects-menu-<slug>/``) at ready() time, before the URLconf freezes —
    each reverses for any slug, including COTs created after startup.  New/changed
    ``menu_name`` values need a restart to add a route (same constraint as the
    built-in per-menu tabs); the tab CONTENTS update live per request.
    """
    try:
        import netbox_custom_objects.urls as co_urls
        from django.urls import path as url_path
    except ImportError:
        return

    existing_names = {p.name for p in co_urls.urlpatterns if hasattr(p, 'name') and p.name}
    for menu_name in _distinct_menu_names():
        url_name = _co_menu_url_name(menu_name)
        if url_name in existing_names:
            continue
        slug = _menu_tab_slug(menu_name)
        full_path = f'<str:custom_object_type>/<int:pk>/custom-objects-menu-{slug}/'
        co_urls.urlpatterns.append(
            url_path(full_path, make_co_menu_view(menu_name).as_view(), name=url_name)
        )
        existing_names.add(url_name)
        logger.debug("injected per-menu URL pattern '%s'", url_name)


def _public_host_model_classes():
    """
    Return the model classes a combined "Custom Objects" tab may need to appear on.

    These are the models a CustomObjectType OBJECT/MULTIOBJECT field can target —
    ``ObjectType.objects.public()`` (the same flag the field's form picker uses)
    minus this plugin's own app (custom-object hosts use the generic injected URL,
    see ``_inject_co_urls``). Registering on all of them at startup is what makes a
    newly-referenced model's tab live without a restart (see ``register_tabs``).

    Returns ``[]`` if the database isn't usable yet (fresh install before
    ``migrate``); registration is retried on the next process start.
    """
    from core.models import ObjectType
    from django.db.utils import OperationalError, ProgrammingError

    try:
        object_types = list(ObjectType.objects.public().exclude(app_label=APP_LABEL))
    except (OperationalError, ProgrammingError):
        logger.warning('database unavailable — combined tab not registered until next start')
        return []

    seen = set()
    result = []
    for ot in object_types:
        # Log the stored app_label/model columns, not str(ot): when the model class
        # is gone, str(ot) renders as "None > None" and hides which ObjectType is the
        # problem.  The columns still point at the culprit (e.g. an uninstalled plugin).
        try:
            model = ot.model_class()
        except Exception:
            logger.exception(
                'skipping ObjectType pk=%s (%s.%s): error resolving its model class',
                ot.pk, ot.app_label, ot.model,
            )
            continue
        if model is None:
            logger.warning(
                'skipping ObjectType pk=%s (%s.%s): no installed model — likely a stale row from an '
                'uninstalled plugin or a deleted Custom Object Type',
                ot.pk, ot.app_label, ot.model,
            )
            continue
        key = (model._meta.app_label, model._meta.model_name)
        if key in seen:
            continue
        seen.add(key)
        result.append(model)

    return result


def register_tabs():
    """
    Register the combined "Custom Objects" tab.

    Called from ``CustomObjectsPluginConfig.ready()`` as a third pass, after the
    existing two-pass model + serializer registration.  Two host kinds:

    * **Built-in NetBox models** — the tab view is registered on every public
      model (``_public_host_model_classes``), so each model's per-model URL is
      baked by ``get_model_urls()`` when its app's ``urls.py`` is imported at
      URLconf freeze.  The tab shows only when its live badge is non-zero
      (``hide_if_empty``), so registering broadly is cheap and a newly-referenced
      model's tab is live on the next request — no restart.

    * **Custom-object host pages (CO→CO)** — served by a single COT-agnostic URL
      injected here (``_inject_co_urls``) plus the live ``custom_objects_tab_link``
      template tag.

    All registration must happen synchronously here: NetBox builds each model's
    URLconf (via ``get_model_urls()``) on the first ``resolve()`` call,
    snapshotting ``registry['views']`` at that moment; anything added later has no
    URL pattern.  Likewise, ``_inject_co_urls()`` mutates
    ``netbox_custom_objects.urls.urlpatterns`` and must run before the URL
    resolver populates its lookup cache against that list.
    """
    from django.urls import clear_url_caches

    try:
        # Inject the generic custom-object combined-tab URL first and
        # unconditionally.  It is a single COT-agnostic route, so it must exist at
        # startup (the URLconf freezes after ready()) to serve combined tabs on
        # custom-object host pages — including CustomObjectTypes created later
        # (CO→CO references).
        _inject_co_urls()
        # Inject one COT-agnostic route per distinct menu_name so per-menu-name
        # tabs work on custom-object host pages (CO→CO), mirroring the combined
        # tab's injected route above.
        _inject_co_menu_urls()
        host_models = _public_host_model_classes()
        register_combined_tabs(host_models, COMBINED_LABEL, COMBINED_WEIGHT)
        # Register one separate related tab per distinct, non-empty menu_name on the
        # same built-in host models.  New/changed menu_name values need a restart to
        # add or remove a tab (the URLconf and view registry freeze at startup); the
        # tab CONTENTS update live per request.
        register_menu_name_tabs(host_models)
    finally:
        # Always drop URL-resolver caches once we've mutated urlpatterns / the
        # view registry — even if model enumeration raised partway through.  A
        # resolver cache built earlier in ready() (by other plugins) would
        # otherwise leave the injected CO→CO route unresolvable until a restart.
        clear_url_caches()
