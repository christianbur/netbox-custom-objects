from django import template
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.module_loading import import_string
from netbox.registry import registry
from utilities.views import get_action_url

__all__ = (
    'plugin_extra_tabs',
    'custom_objects_tab_link',
    'custom_objects_menu_tab_links',
    'cot_view_tab_links',
)

register = template.Library()

# journal/changelog/contacts/custom_objects are rendered as hardcoded <li>s, not
# from the registry, so they're excluded here to avoid duplicate, never-active tabs:
# upstream's journal/changelog/contacts views set the active-tab marker as a string
# that ``model_view_tabs`` can't match (contacts is wired to the slug-based
# ``customobject_contacts`` route via NetBox's ContactsMixin), and custom_objects is
# rendered live by ``custom_objects_tab_link`` (so CO->CO tabs appear without a restart).
_HARDCODED_TAB_NAMES = frozenset({'journal', 'changelog', 'contacts', 'custom_objects'})


@register.inclusion_tag('tabs/model_view_tabs.html', takes_context=True)
def plugin_extra_tabs(context, instance):
    """
    Render registered model-view tabs for `instance`, excluding tabs that the
    Custom Object detail template already renders by hand (Journal, Changelog,
    and the combined Custom Objects tab — see _HARDCODED_TAB_NAMES).
    """
    app_label = instance._meta.app_label
    model_name = instance._meta.model_name
    user = context['request'].user
    tabs = []

    try:
        views = registry['views'][app_label][model_name]
    except KeyError:
        views = []

    for config in views:
        if config['name'] in _HARDCODED_TAB_NAMES:
            continue
        view = import_string(config['view']) if type(config['view']) is str else config['view']
        if tab := getattr(view, 'tab', None):
            if tab.permission and not user.has_perm(tab.permission):
                continue
            if attrs := tab.render(instance):
                try:
                    url = get_action_url(instance, action=config['name'], kwargs={'pk': instance.pk})
                except NoReverseMatch:
                    continue
                tabs.append(
                    {
                        'name': config['name'],
                        'url': url,
                        'label': attrs['label'],
                        'badge': attrs['badge'],
                        'weight': attrs['weight'],
                        'is_active': context.get('tab') == tab,
                    }
                )

    tabs = sorted(tabs, key=lambda x: x['weight'])
    return {'tabs': tabs}


@register.inclusion_tag('netbox_custom_objects/related_tabs/combined/tab_link.html', takes_context=True)
def custom_objects_tab_link(context, instance):
    """
    Render the combined "Custom Objects" tab nav-link on a custom object detail
    page, computed live from the DB (not the startup view registry).

    This is what makes references *between* custom object types live without a
    NetBox restart: the tab's URL is a single COT-agnostic route injected at
    startup (``registry._inject_co_urls``) that reverses for any slug, and the
    nav-link's visibility/badge are recomputed per render here.  Returns an empty
    context (no link) when the badge count is zero (hide_if_empty) or the URL
    can't be reversed (plugin URLs not loaded).
    """
    from netbox_custom_objects.related_tabs.views.combined import COMBINED_LABEL, _count_linked_custom_objects

    badge = _count_linked_custom_objects(instance)
    if not badge:
        return {'tab': None}

    try:
        url = get_action_url(instance, action='custom_objects', kwargs={'pk': instance.pk})
    except NoReverseMatch:
        return {'tab': None}

    # Active iff we are actually on the combined-tab page.  Compare the request
    # path to the tab URL rather than inspecting context['tab']: other plugins may
    # also register ViewTab-bearing views on custom-object models, so a type-based
    # check would light this link up on those tabs too.
    request = context.get('request')
    is_active = request is not None and request.path == url

    return {
        'tab': {
            'url': url,
            'label': COMBINED_LABEL,
            'badge': badge,
            'is_active': is_active,
        }
    }


@register.inclusion_tag('netbox_custom_objects/related_tabs/combined/menu_tab_links.html', takes_context=True)
def custom_objects_menu_tab_links(context, instance):
    """
    Render the per-menu-name tab nav-links on a custom object detail page,
    computed live from the DB (not the startup view registry).

    These are the custom-object-host (CO→CO) analogue of the per-menu-name tabs
    that ``register_menu_name_tabs`` registers on built-in host models: a
    CustomObjectType with a non-empty ``menu_name`` is excluded from the combined
    "Custom Objects" tab and surfaced in its own tab.  The URL for each is a
    COT-agnostic route injected at startup (``registry._inject_co_menu_urls``)
    that reverses for any slug; the badge/visibility are recomputed per render
    here, so a link only appears when the user can see ≥1 linked object of that
    menu_name (hide_if_empty).
    """
    from netbox_custom_objects.related_tabs.views.combined import (
        _count_linked_custom_objects,
        _distinct_menu_names,
        _menu_tab_slug,
    )

    request = context.get('request')
    tabs = []
    for menu_name in _distinct_menu_names():
        badge = _count_linked_custom_objects(instance, menu_filter=menu_name)
        if not badge:
            continue
        action = f"custom_objects_menu_{_menu_tab_slug(menu_name).replace('-', '_')}"
        try:
            url = get_action_url(instance, action=action, kwargs={'pk': instance.pk})
        except NoReverseMatch:
            continue
        tabs.append(
            {
                'url': url,
                'label': menu_name,
                'badge': badge,
                'is_active': request is not None and request.path == url,
            }
        )
    return {'tabs': tabs}


@register.inclusion_tag('netbox_custom_objects/cot_views/tab_links.html', takes_context=True)
def cot_view_tab_links(context, instance):
    """
    Render a nav-link for each COT view selected on this object's type.

    The binding is dynamic: ``CustomObjectType.views`` lists the chosen registry
    keys, and each key that is also present in the in-process registry gets a
    tab.  A selected-but-unregistered key (its bundle is disabled or the
    workers haven't restarted) is silently skipped.
    """
    from netbox_custom_objects.cot_views.registry import get_cot_view

    cot = getattr(instance, 'custom_object_type', None)
    if cot is None:
        return {'tabs': []}

    request = context.get('request')
    tabs = []
    for key in cot.get_view_keys():
        view_cls = get_cot_view(key)
        if view_cls is None:
            continue
        try:
            url = reverse(
                'plugins:netbox_custom_objects:customobject_cot_view',
                kwargs={'custom_object_type': cot.slug, 'pk': instance.pk, 'view_key': key},
            )
        except NoReverseMatch:
            continue
        tabs.append(
            {
                'url': url,
                'label': view_cls.label or key,
                'weight': getattr(view_cls, 'weight', 2100),
                'is_active': request is not None and request.path == url,
            }
        )
    tabs = sorted(tabs, key=lambda t: t['weight'])
    return {'tabs': tabs}
