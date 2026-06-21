import logging
from collections import defaultdict
from types import SimpleNamespace
from urllib.parse import urlencode

import django_tables2 as tables2
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import InvalidPage
from django.db.models import Q, prefetch_related_objects
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import View
from extras.choices import CustomFieldTypeChoices
from netbox.context import current_request
from netbox.plugins import get_plugin_config
from netbox.registry import registry
from netbox.tables import BaseTable
from netbox_custom_objects.models import CustomObjectTypeField
from netbox_custom_objects.utilities import restrict_to_viewable
from utilities.htmx import htmx_partial
from utilities.paginator import EnhancedPaginator, get_paginate_count
from utilities.views import ConditionalLoginRequiredMixin, ViewTab, register_model_view

logger = logging.getLogger('netbox_custom_objects.related_tabs')

_CUSTOM_OBJECTS_APP = 'netbox_custom_objects'
# Dynamic CO models use a single shared detail template; per-model templates don't exist.
_CO_BASE_TEMPLATE = 'netbox_custom_objects/customobject.html'

# Single source for the tab label/weight (factory, CO->CO view, registry, template tag).
COMBINED_LABEL = 'Custom Objects'
COMBINED_WEIGHT = 2000


def _get_base_template(instance):
    """Return the correct base_template for an object's detail page."""
    if instance._meta.app_label == _CUSTOM_OBJECTS_APP:
        return _CO_BASE_TEMPLATE
    return f'{instance._meta.app_label}/{instance._meta.model_name}.html'


def _restrict_or_warn(qs, user, *, label):
    """
    Apply NetBox's per-row ``.restrict(user, 'view')`` to ``qs``.

    If the queryset's manager doesn't implement ``.restrict()`` (rare — only
    models whose manager isn't a RestrictedQuerySet), log a warning and return
    ``qs`` unrestricted, so a silent permission bypass is observable in logs
    rather than invisible.
    """
    try:
        return qs.restrict(user, 'view')
    except AttributeError:
        logger.warning('%s lacks restrict(user, view); per-row permission filter skipped', label)
        return qs


def _unique_sorted(items, *, key, sort_key):
    """De-duplicate ``items`` by ``key(item)`` (first occurrence wins), sorted by ``sort_key``."""
    seen = set()
    unique = []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            unique.append(item)
    return sorted(unique, key=sort_key)


def reference_q(host_ct_id, host_pk, field_name, field_type, is_polymorphic, through_model_name=None):
    """
    Build a Q selecting custom-object rows whose ``field_name`` references the host
    object identified by (``host_ct_id``, ``host_pk``).  Single source of truth for
    the four reference shapes the combined tab view filters on:

      * OBJECT, non-polymorphic      -> ``{name}_id``
      * OBJECT, polymorphic          -> ``{name}_content_type_id`` + ``{name}_object_id``
      * MULTIOBJECT, non-polymorphic -> ``{name}`` (reverse M2M)
      * MULTIOBJECT, polymorphic     -> ``pk__in`` subquery over the field's through table

    Returns an EMPTY ``Q()`` for an unsupported field type or an unresolvable
    polymorphic through model.  Callers MUST treat an empty Q as "matches nothing /
    skip" and never pass it to ``.filter()`` directly — ``filter(Q())`` matches
    every row (an empty Q is the identity element for ``|``).
    """
    if field_type == CustomFieldTypeChoices.TYPE_OBJECT:
        if is_polymorphic:
            return Q(**{f'{field_name}_content_type_id': host_ct_id, f'{field_name}_object_id': host_pk})
        return Q(**{f'{field_name}_id': host_pk})

    if field_type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
        if is_polymorphic:
            try:
                through = apps.get_model(_CUSTOM_OBJECTS_APP, through_model_name)
            except LookupError:
                logger.exception(
                    'Could not resolve through model %r for polymorphic field %s', through_model_name, field_name
                )
                return Q()
            return Q(pk__in=through.objects.filter(content_type_id=host_ct_id, object_id=host_pk).values('source_id'))
        return Q(**{field_name: host_pk})

    return Q()


def _register_tab_view(model_class, name, path, view_factory):
    """
    Register a model-view tab on ``model_class``, building it via ``view_factory``.

    Idempotent: if a tab with this ``name`` already exists for the model, log and
    skip — this guards against the Django autoreloader re-running registration.
    ``view_factory`` is a zero-arg callable so the view class isn't built on the
    already-registered path.

    Returns True if registered, False if skipped.
    """
    app_label = model_class._meta.app_label
    model_name = model_class._meta.model_name
    existing = registry['views'].get(app_label, {}).get(model_name, [])
    if any(entry['name'] == name for entry in existing):
        logger.debug('tab %r already registered for %s.%s — skipping', name, app_label, model_name)
        return False
    register_model_view(model_class, name=name, path=path)(view_factory())
    logger.debug('registered tab %r for %s.%s', name, app_label, model_name)
    return True


class CustomObjectsTabTable(BaseTable):
    """Lightweight table class used only for column-preference machinery."""

    type = tables2.Column(verbose_name=_('Type'), orderable=False)
    object = tables2.Column(verbose_name=_('Object'), orderable=False)
    value = tables2.Column(verbose_name=_('Value'), orderable=False)
    field = tables2.Column(verbose_name=_('Field'), orderable=False)
    tags = tables2.Column(verbose_name=_('Tags'), orderable=False)
    actions = tables2.Column(verbose_name='', orderable=False)

    exempt_columns = ('actions',)

    class Meta(BaseTable.Meta):
        fields = ('type', 'object', 'value', 'field', 'tags', 'actions')
        default_columns = ('type', 'object', 'value', 'field', 'tags', 'actions')


def _max_multiobject_display():
    """Max related objects shown in a MULTIOBJECT Value column (PLUGINS_CONFIG, default 3)."""
    value = get_plugin_config(_CUSTOM_OBJECTS_APP, 'max_multiobject_display')
    # Operator-supplied: fall back to the default on a non-positive int so a
    # misconfigured value can't crash the detail page (see checks.W003).
    return value if isinstance(value, int) and value >= 1 else 3


def _iter_linked_fields(instance):
    """
    Yield (field, model, q) for every CO field referencing instance, where ``q``
    is a non-empty Q selecting the rows of that field's model that reference the
    instance.

    Handles both non-polymorphic (related_object_type FK) and polymorphic
    (related_object_types M2M) fields via ``reference_q``; fields whose Q comes
    back empty are skipped, so callers never filter on an empty Q.
    """
    content_type = ContentType.objects.get_for_model(instance._meta.model)
    type_choices = [CustomFieldTypeChoices.TYPE_OBJECT, CustomFieldTypeChoices.TYPE_MULTIOBJECT]

    # Fast path: the tab is registered on every public model, so this runs on every
    # detail-page render. One existence check short-circuits the two queries below
    # when nothing references this model. The predicate must mirror those two
    # querysets exactly so a False result guarantees both are empty.
    if not CustomObjectTypeField.objects.filter(
        Q(related_object_type=content_type, is_polymorphic=False)
        | Q(related_object_types=content_type, is_polymorphic=True),
        type__in=type_choices,
    ).exists():
        return

    # is_polymorphic=False keeps the two querysets disjoint — a row with
    # related_object_type set AND is_polymorphic=True (a legacy misconfig:
    # is_polymorphic is immutable upstream but related_object_type isn't
    # nulled when toggled) would otherwise be yielded twice.
    non_poly = CustomObjectTypeField.objects.filter(
        related_object_type=content_type,
        is_polymorphic=False,
        type__in=type_choices,
    ).select_related('custom_object_type')

    poly = CustomObjectTypeField.objects.filter(
        related_object_types=content_type,
        is_polymorphic=True,
        type__in=type_choices,
    ).select_related('custom_object_type')

    # One CustomObjectType can contribute several referencing fields (e.g. a
    # polymorphic and a non-polymorphic one); resolve its model once per render.
    model_cache = {}
    for field in list(non_poly) + list(poly):
        cot_id = field.custom_object_type_id
        model = model_cache.get(cot_id)
        if model is None:
            try:
                model = field.custom_object_type.get_model()
            except Exception:
                logger.exception('Could not get model for CustomObjectType %s', cot_id)
                continue
            model_cache[cot_id] = model
        q = reference_q(
            content_type.id, instance.pk, field.name, field.type, field.is_polymorphic, field.through_model_name
        )
        if not q.children:
            # Empty Q == "matches nothing" (unresolvable through model); skip it —
            # filtering on an empty Q would match every row of this model.
            continue
        yield field, model, q


# Request attribute under which _linked_fields stashes its per-instance memo.
_LINKED_FIELDS_REQUEST_CACHE = '_co_combined_linked_fields'


def _linked_fields(instance):
    """
    Request-cached materialization of ``_iter_linked_fields(instance)``.

    The body render (``_get_linked_custom_objects``) and the ViewTab badge
    (``_count_linked_custom_objects``) both need the same ``(field, model, q)``
    triples, and building them calls ``get_model()`` per linked type — the costly
    part. Memoizing on the request collapses those two passes into one.

    Keyed by ``(model label, pk)``; the triples are user-independent (per-row
    ``.restrict()`` happens in each caller), so the cache is shared safely. No
    request context (shell, jobs) -> fresh build.
    """
    request = current_request.get()
    if request is None:
        return list(_iter_linked_fields(instance))
    cache = getattr(request, _LINKED_FIELDS_REQUEST_CACHE, None)
    if cache is None:
        cache = {}
        setattr(request, _LINKED_FIELDS_REQUEST_CACHE, cache)
    key = (instance._meta.label, instance.pk)
    if key not in cache:
        cache[key] = list(_iter_linked_fields(instance))
    return cache[key]


# ---------------------------------------------------------------------------
# Custom Object Type enhancements: menu split, outgoing refs, junction traversal
#
# These build on the per-COT fields added in migration 0015
# (``menu_name``, ``link_table``, ``metadata``).  All logic is wrapped
# defensively so a misconfigured type can never crash a detail page or the menu.
# ---------------------------------------------------------------------------

# Sentinel ``menu_filter`` value: the combined tab, i.e. only rows whose owning
# CustomObjectType has an empty ``menu_name``.  A concrete string means "only
# rows whose owning type has that exact ``menu_name``".
COMBINED_MENU = object()


def _cot_menu_name(cot):
    """Normalised ``menu_name`` of a CustomObjectType ("" when unset/unreadable)."""
    if cot is None:
        return ''
    return (getattr(cot, 'menu_name', '') or '').strip()


def _field_menu_name(field):
    """``menu_name`` of the CustomObjectType that owns a (possibly proxy) field."""
    return _cot_menu_name(getattr(field, 'custom_object_type', None))


def _row_matches_menu(field, menu_filter):
    """Whether a row owned by ``field`` belongs to the ``menu_filter`` tab."""
    menu_name = _field_menu_name(field)
    if menu_filter is COMBINED_MENU:
        return not menu_name
    return menu_name == menu_filter


def _filter_rows_by_menu(rows, menu_filter):
    """Keep only the ``(obj, field)`` rows belonging to ``menu_filter``."""
    try:
        return [(obj, field) for obj, field in rows if _row_matches_menu(field, menu_filter)]
    except Exception:
        logger.exception('menu-name row filter failed; returning unfiltered rows')
        return rows


def _cot_is_junction(cot):
    """True when a CustomObjectType is flagged as an n:m link table."""
    return bool(getattr(cot, 'link_table', False))


def _object_fields_for_cot(cot):
    """The OBJECT / MULTIOBJECT fields defined on a CustomObjectType."""
    return list(
        CustomObjectTypeField.objects.filter(
            custom_object_type=cot,
            type__in=[CustomFieldTypeChoices.TYPE_OBJECT, CustomFieldTypeChoices.TYPE_MULTIOBJECT],
        )
    )


def _field_has_value(instance, field):
    """Whether ``instance`` has a non-empty value for one of its own object fields."""
    value = getattr(instance, field.name, None)
    if field.type == CustomFieldTypeChoices.TYPE_OBJECT:
        return value is not None
    try:
        return value is not None and value.exists()
    except Exception:
        return False


def _type_label(endpoint):
    """A human label for a junction far-endpoint (COT name or model verbose name)."""
    cot = getattr(endpoint, 'custom_object_type', None)
    if cot is not None:
        return str(cot)
    try:
        return endpoint._meta.verbose_name.title()
    except Exception:
        return type(endpoint).__name__


class _OutgoingFieldProxy:
    """Wrapper around a CustomObjectTypeField that only overrides ``__str__``.

    Used for OUTGOING rows so the Field column carries a direction-aware label
    while every other attribute (``name``, ``type``, ``is_polymorphic``,
    ``custom_object_type``, …) delegates to the real field — keeping the tab's
    value resolution, batching and sorting working unchanged.
    """

    is_junction_row = False
    # Type-column label for OUTGOING rows on a link_table host. None for ordinary
    # hosts (Type then shows the owning COT); set to the far endpoint's type label
    # for a junction host so the column shows the value's type, not the junction COT.
    type_label = None

    def __init__(self, field, label):
        object.__setattr__(self, '_field', field)
        object.__setattr__(self, '_label', label)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_field'), name)

    def __str__(self):
        return object.__getattribute__(self, '_label')


class _JunctionField:
    """Synthetic "field" describing a junction-resolved row.

    The row's ``obj`` is the far endpoint the junction connects to; this field
    carries what the template needs to render it: a type label, the junction
    object (shown as "via" and used for the row actions) and the Field-column
    label.  ``type`` is a sentinel so the value resolver / batcher skip it — the
    template renders these rows through its ``is_junction_row`` branch instead.
    """

    is_junction_row = True
    type = '_junction'
    is_polymorphic = False
    name = '_junction'

    def __init__(self, junction_cot, type_label, via_obj, label):
        self.custom_object_type = junction_cot
        self.type_label = type_label
        self.via_obj = via_obj
        self._label = label

    def __str__(self):
        return self._label


def _far_field(near_field):
    """The *other* object field on a junction COT (the far endpoint of the link)."""
    cot = getattr(near_field, 'custom_object_type', None)
    if cot is None:
        return None
    others = [f for f in _object_fields_for_cot(cot) if f.name != near_field.name]
    return others[0] if len(others) == 1 else None


def _transform_junctions(rows):
    """Rewrite junction rows so the row's object is the far endpoint.

    ``rows`` are ``(junction_obj, near_field)`` (the junction matched the host on
    ``near_field``).  For a junction COT with exactly two object fields we resolve
    the other field to the far endpoint and emit ``(endpoint, _JunctionField)`` so
    the endpoint becomes the primary Object, with the junction demoted to "via".
    Any row whose far endpoint can't be resolved to a single linkable object is
    left untouched, and ``obj`` always stays a real, linkable object.
    """
    out = []
    for obj, field in rows:
        try:
            cot = getattr(field, 'custom_object_type', None)
            if _cot_is_junction(cot):
                far = _far_field(field)
                endpoint = getattr(obj, far.name, None) if far is not None else None
                if endpoint is not None and hasattr(endpoint, 'get_absolute_url'):
                    jf = _JunctionField(cot, _type_label(endpoint), obj, _('linked via %(cot)s') % {'cot': cot})
                    out.append((endpoint, jf))
                    continue
        except Exception:
            logger.exception('junction traversal failed for a row; leaving it untouched')
        out.append((obj, field))
    return out


def _outgoing_far_type_label(instance, field):
    """Type label for an OUTGOING row on a link_table host: the value's far type.

    Mirrors the junction-transform Type column (``_type_label``) so a junction's
    own detail page shows the endpoint's type (COT name, or NetBox model label)
    instead of the junction COT.  Returns ``None`` when no single far type can be
    resolved (e.g. an empty or mixed MULTIOBJECT), letting the Type column fall
    back to the owning COT.
    """
    value = getattr(instance, field.name, None)
    if value is None:
        return None
    if field.type == CustomFieldTypeChoices.TYPE_OBJECT:
        return _type_label(value)
    try:
        first = value.all().first()
    except Exception:
        return None
    return _type_label(first) if first is not None else None


def _outgoing_rows(instance):
    """The host's own OBJECT/MULTIOBJECT field targets, as combined-tab rows.

    Returns ``[]`` for built-in (non custom-object) hosts, which own no COT
    fields.  Each emitted row keeps ``instance`` as ``obj`` (so the row actions
    target a real custom object) and surfaces the target in the Value column.

    On a ``link_table`` (junction) host the Type column would otherwise show the
    junction COT for every row; instead each row's proxy carries a ``type_label``
    of its far endpoint's type, matching the incoming junction-transform view.
    """
    cot = getattr(instance, 'custom_object_type', None)
    if cot is None:
        return []
    is_junction = _cot_is_junction(cot)
    rows = []
    try:
        for field in _object_fields_for_cot(cot):
            if _field_has_value(instance, field):
                label = _('%(field)s (this object \u2192 value)') % {'field': field}
                proxy = _OutgoingFieldProxy(field, label)
                if is_junction:
                    proxy.type_label = _outgoing_far_type_label(instance, field)
                rows.append((instance, proxy))
    except Exception:
        logger.exception('could not build outgoing reference rows for %s', instance)
    return rows


def _get_linked_custom_objects(instance, user=None, menu_filter=COMBINED_MENU):
    """
    Return list of (object, CustomObjectTypeField) tuples for the combined tab.

    Includes three kinds of row:

    * **incoming** — custom objects that reference ``instance`` via an OBJECT or
      MULTIOBJECT field (the original behaviour);
    * **junction** — incoming rows whose owning type is a ``link_table``
      n:m link table are rewritten to their far endpoint (see
      ``_transform_junctions``);
    * **outgoing** — for custom-object hosts, the host's own OBJECT/MULTIOBJECT
      targets (see ``_outgoing_rows``).

    Rows are then partitioned by ``menu_filter`` so each tab shows only the types
    that belong to it (``COMBINED_MENU`` → types with an empty ``menu_name``; a
    string → types with that ``menu_name``).

    When ``user`` is given, incoming rows are filtered through NetBox's per-row
    ``.restrict(user, 'view')`` so callers don't leak rows the user can't see.
    """
    results = []
    for field, model, q in _linked_fields(instance):
        qs = model.objects.filter(q).prefetch_related('tags')
        # A non-polymorphic OBJECT field's Value is an FK; prime it so the per-row
        # _get_field_value getattr doesn't issue one extra query per row.
        if field.type == CustomFieldTypeChoices.TYPE_OBJECT and not field.is_polymorphic:
            qs = qs.select_related(field.name)
        if user is not None:
            qs = _restrict_or_warn(qs, user, label=model._meta.label)
        for obj in qs:
            results.append((obj, field))

    results = _transform_junctions(results)
    results.extend(_outgoing_rows(instance))
    return _filter_rows_by_menu(results, menu_filter)


def _count_linked_custom_objects(instance, menu_filter=COMBINED_MENU):
    """
    Badge callable for ViewTab.

    Counts the rows shown by ``_get_linked_custom_objects`` for ``instance`` and
    the given ``menu_filter``, restricted to what the current request's user may
    view — so the badge matches the visible rows and ``hide_if_empty`` hides the
    tab when the user can see none.  The user is read from NetBox's
    ``current_request`` ContextVar (the ViewTab badge signature passes only the
    instance); with no request context (shell, jobs) the count is unrestricted.

    Unlike the original COUNT(*), this materialises the rows because junction
    traversal and outgoing references are computed in Python — the same list the
    tab body renders, so the count can never disagree with what is shown.
    Returns None (not 0) when empty so ``hide_if_empty`` works.
    """
    request = current_request.get()
    user = getattr(request, 'user', None) if request is not None else None
    total = len(_get_linked_custom_objects(instance, user=user, menu_filter=menu_filter))
    return total if total > 0 else None


def _filter_linked_objects(linked, q):
    """
    Case-insensitive substring search across the object display name,
    custom object type name, and field label.
    """
    q = q.strip().lower()
    if not q:
        return linked
    return [
        (obj, field)
        for obj, field in linked
        if q in str(obj).lower() or q in str(field.custom_object_type).lower() or q in str(field).lower()
    ]


def _get_field_value(obj, field, user=None):
    """
    Return the value stored in `field` on `obj`, for display in the Value column.

    TYPE_OBJECT     → the related model instance (or None if unset)
    TYPE_MULTIOBJECT → list of related instances, up to max_multiobject_display + 1
                       (the extra item lets the template detect truncation without a
                       separate COUNT query)

    When ``user`` is given, MULTIOBJECT targets are filtered by 'view' permission
    so the Value column never discloses related objects the user cannot see —
    matching the per-row ``.restrict`` applied to the linked rows themselves.
    Non-polymorphic targets are a queryset (filtered in SQL via ``.restrict``);
    polymorphic targets are a plain result list spanning several models, filtered
    via ``restrict_to_viewable``.
    """
    if field.type == CustomFieldTypeChoices.TYPE_OBJECT:
        return getattr(obj, field.name, None)
    if field.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
        manager = getattr(obj, field.name, None)
        if manager is None:
            return []
        limit = _max_multiobject_display() + 1
        qs = manager.all()
        if user is not None:
            try:
                qs = qs.restrict(user, 'view')
            except AttributeError:
                # Polymorphic targets: not a queryset (no .restrict) — filter the
                # heterogeneous result list, then truncate.
                return restrict_to_viewable(user, list(qs))[:limit]
        return list(qs[:limit])
    return None


def _batch_multiobject_values(pairs, user=None):
    """
    Bulk-resolve the Value column for the page's non-polymorphic MULTIOBJECT rows.

    Per-row resolution (``_get_field_value`` -> ``manager.all()``) costs one
    through-table + one target query per row — the N+1 that dominates the tab's
    query count. Instead each ``(model, field)`` group is prefetched once via
    ``CustomManyToManyManager.get_prefetch_querysets`` and read from cache.

    Returns ``{(id(obj), id(field)): [targets up to max_multiobject_display + 1]}``.
    OBJECT and polymorphic MULTIOBJECT rows are absent — they stay on the per-row
    path (the polymorphic manager isn't prefetchable and self-batches per type).
    Targets are permission-filtered via ``restrict_to_viewable``; prefetch
    fetches every target per row, not just the displayed slice — fine for the cap.
    """
    limit = _max_multiobject_display() + 1
    groups = defaultdict(list)
    field_by_key = {}
    for obj, field in pairs:
        if field.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT and not field.is_polymorphic:
            groups[id(field)].append(obj)
            field_by_key[id(field)] = field

    resolved = {}
    for key, objs in groups.items():
        field = field_by_key[key]
        # One prefetch per (model, field) group; objs are homogeneous because the
        # same field object is reused across all of its rows (see _iter_linked_fields).
        prefetch_related_objects(objs, field.name)
        per_obj_targets = {
            id(obj): list(getattr(obj, '_prefetched_objects_cache', {}).get(field.name, []))
            for obj in objs
        }
        if user is not None:
            # All targets in the group share one model (non-polymorphic field), so a
            # single restrict_to_viewable() resolves the whole group in one query.
            all_targets = [t for targets in per_obj_targets.values() for t in targets]
            viewable_pks = {t.pk for t in restrict_to_viewable(user, all_targets)}
            per_obj_targets = {
                oid: [t for t in targets if t.pk in viewable_pks]
                for oid, targets in per_obj_targets.items()
            }
        for obj in objs:
            resolved[(id(obj), key)] = per_obj_targets[id(obj)][:limit]
    return resolved


# Sort keys by ?sort= value.
_SORT_KEYS = {
    'type': lambda t: str(t[1].custom_object_type).lower(),
    'object': lambda t: str(t[0]).lower(),
    'field': lambda t: str(t[1]).lower(),
}


def _sort_header(col, base_params, sort_field, descending):
    """
    Build a native-style sortable column header descriptor.

    NetBox's object-list tables sort with a single ``?sort=`` param (a ``-``
    prefix means descending) and mark the active column's ``<th>`` with an
    ``asc``/``desc`` class plus a "clear ordering" link.  Returns a dict the
    template renders:

      th_class   – 'asc' | 'desc' | '' (combined with the always-present 'orderable')
      is_active  – True if this column is the current sort column
      url        – ?sort=… for the header link (toggles asc⇄desc when active)
      clear_url  – ?sort cleared, preserving the other filters (shown when active)
    """
    is_active = col == sort_field
    if is_active:
        th_class = 'desc' if descending else 'asc'
        # Toggle direction on repeat click: asc -> desc -> asc …
        next_param = col if descending else f'-{col}'
    else:
        th_class = ''
        next_param = col

    url = '?' + urlencode({**base_params, 'sort': next_param})
    clear_url = '?' + urlencode(base_params) if base_params else '?'
    return {'th_class': th_class, 'is_active': is_active, 'url': url, 'clear_url': clear_url}


def _render_combined_tab(request, instance, tab, menu_filter=COMBINED_MENU):
    """
    Render the combined "Custom Objects" tab for ``instance`` (search / type /
    tag filters, sort, HTMX pagination).  Shared by the built-in-host view
    (``_make_tab_view``) and the generic custom-object-host view
    (``make_co_combined_view``) so both render identically.

    ``menu_filter`` selects which types appear: ``COMBINED_MENU`` (the default)
    renders only types with an empty ``menu_name``; a string renders only the
    types whose ``menu_name`` matches it (used by the per-menu-name tabs).
    """
    linked_all = _get_linked_custom_objects(instance, user=request.user, menu_filter=menu_filter)

    # Build table object for column-preference machinery (no data, just column config)
    tab_table = CustomObjectsTabTable([], empty_text='')
    visible_cols = None
    if request.user.is_authenticated and (userconfig := getattr(request.user, 'config', None)):
        visible_cols = userconfig.get(f'tables.{tab_table.name}.columns')
    if visible_cols is None:
        visible_cols = list(CustomObjectsTabTable.Meta.default_columns)
    tab_table._set_columns(visible_cols)
    selected_columns = {col for col, _ in tab_table.selected_columns} | set(tab_table.exempt_columns)

    # Type dropdown — always from the unfiltered list
    available_types = _unique_sorted(
        (field.custom_object_type for _obj, field in linked_all),
        key=lambda cot: cot.pk,
        sort_key=str,
    )

    q = request.GET.get('q', '')
    type_slug = request.GET.get('type', '')
    tag_slug = request.GET.get('tag', '').strip()
    sort_param = request.GET.get('sort', '')
    sort_descending = sort_param.startswith('-')
    sort_field = sort_param[1:] if sort_descending else sort_param
    per_page = request.GET.get('per_page', '')

    # Tag dropdown — always from the unfiltered list
    available_tags = _unique_sorted(
        (t for obj, _field in linked_all for t in obj.tags.all()),
        key=lambda t: t.slug,
        sort_key=lambda t: t.name.lower(),
    )

    linked = _filter_linked_objects(linked_all, q)
    if type_slug:
        linked = [(obj, field) for obj, field in linked if field.custom_object_type.slug == type_slug]
    if tag_slug:
        linked = [(obj, field) for obj, field in linked if tag_slug in {t.slug for t in obj.tags.all()}]

    # In-memory sort
    if sort_field in _SORT_KEYS:
        linked.sort(key=_SORT_KEYS[sort_field], reverse=sort_descending)

    paginator = EnhancedPaginator(linked, get_paginate_count(request))
    try:
        page = paginator.page(int(request.GET.get('page', 1)))
    except (InvalidPage, ValueError):
        page = paginator.page(1)

    # Resolve values for the current page only — avoids N+1 on the full list.
    # Non-polymorphic MULTIOBJECT values are batch-prefetched per (model, field);
    # everything else falls back to the per-row resolver.
    page_pairs = list(page.object_list)
    multiobject_values = _batch_multiobject_values(page_pairs, request.user)
    page_rows = [
        (
            obj,
            field,
            multiobject_values[(id(obj), id(field))]
            if (id(obj), id(field)) in multiobject_values
            else _get_field_value(obj, field, request.user),
        )
        for obj, field in page_pairs
    ]

    # Filters preserved on the column sort links (each link adds its own ?sort=)
    base_params = {
        key: value
        for key, value in (('q', q), ('type', type_slug), ('tag', tag_slug), ('per_page', per_page))
        if value
    }

    sort_headers = {
        col: _sort_header(col, base_params, sort_field, sort_descending) for col in ('type', 'object', 'field')
    }

    context = {
        'object': instance,
        'tab': tab,
        # Parent model's detail template, so tabs/breadcrumbs/header render.
        'base_template': _get_base_template(instance),
        'page_obj': page,
        'paginator': paginator,
        'page_rows': page_rows,
        'q': q,
        'type_slug': type_slug,
        'tag_slug': tag_slug,
        'available_types': available_types,
        'available_tags': available_tags,
        'sort': sort_param,
        'sort_headers': sort_headers,
        'htmx_table': SimpleNamespace(htmx_url=request.path, embedded=False),
        'return_url': request.get_full_path(),
        'tab_table': tab_table,
        'selected_columns': selected_columns,
        'max_multiobject_display': _max_multiobject_display(),
    }

    if htmx_partial(request):
        return render(request, 'netbox_custom_objects/related_tabs/combined/tab_partial.html', context)
    return render(request, 'netbox_custom_objects/related_tabs/combined/tab.html', context)


def _make_tab_view(model_class, label=COMBINED_LABEL, weight=COMBINED_WEIGHT):
    """
    Factory that returns a unique View subclass for a built-in (non custom-object)
    host model.  Each model needs its own class so that NetBox's view registry
    stores separate entries and URL names do not collide.

    Custom-object host pages do NOT use this — they are served by the generic,
    slug-resolving ``make_co_combined_view`` so a brand-new CustomObjectType gets
    a live tab without startup registration.
    """

    class _TabView(ConditionalLoginRequiredMixin, View):
        tab = ViewTab(
            label=label,
            badge=_count_linked_custom_objects,
            weight=weight,
            hide_if_empty=True,
        )

        def get(self, request, pk, **kwargs):
            qs = _restrict_or_warn(model_class.objects.all(), request.user, label=model_class._meta.label)
            instance = get_object_or_404(qs, pk=pk)
            return _render_combined_tab(request, instance, self.tab)

    _TabView.__name__ = f'{model_class.__name__}CustomObjectsTabView'
    _TabView.__qualname__ = f'{model_class.__name__}CustomObjectsTabView'
    return _TabView


def make_co_combined_view(label=COMBINED_LABEL, weight=COMBINED_WEIGHT):
    """
    Return the combined-tab view for *custom-object* host pages.

    Unlike ``_make_tab_view`` (one class per built-in model), this single view
    resolves the target CustomObjectType from the URL slug at request time, so it
    serves any CustomObjectType — including ones created after startup. Its URL is
    injected by ``register_tabs`` and the nav-link is rendered live by the
    ``custom_objects_tab_link`` template tag.
    """

    class _COCombinedTabView(ConditionalLoginRequiredMixin, View):
        tab = ViewTab(
            label=label,
            badge=_count_linked_custom_objects,
            weight=weight,
            hide_if_empty=True,
        )

        def get(self, request, custom_object_type, pk, **kwargs):
            from netbox_custom_objects.models import CustomObjectType

            cot = get_object_or_404(CustomObjectType, slug=custom_object_type)
            actual_model = cot.get_model()
            qs = _restrict_or_warn(actual_model.objects.all(), request.user, label=actual_model._meta.label)
            instance = get_object_or_404(qs, pk=pk)
            return _render_combined_tab(request, instance, self.tab)

    return _COCombinedTabView


def make_co_menu_view(menu_name, weight=COMBINED_WEIGHT + 10):
    """
    Return the per-menu-name tab view for *custom-object* host pages.

    The custom-object analogue of ``_make_menu_tab_view`` (which targets built-in
    host models).  Like ``make_co_combined_view`` it resolves the target
    CustomObjectType from the URL slug at request time, so a single injected
    COT-agnostic route serves every COT — including ones created after startup.
    ``menu_filter`` is pinned to ``menu_name`` so only that menu's linked objects
    appear.  Its URL is injected by ``registry._inject_co_menu_urls`` and the
    nav-link is rendered live by the ``custom_objects_menu_tab_links`` template
    tag.
    """

    def _badge(instance, _menu_name=menu_name):
        return _count_linked_custom_objects(instance, menu_filter=_menu_name)

    class _COMenuTabView(ConditionalLoginRequiredMixin, View):
        tab = ViewTab(label=menu_name, badge=_badge, weight=weight, hide_if_empty=True)

        def get(self, request, custom_object_type, pk, **kwargs):
            from netbox_custom_objects.models import CustomObjectType

            cot = get_object_or_404(CustomObjectType, slug=custom_object_type)
            actual_model = cot.get_model()
            qs = _restrict_or_warn(actual_model.objects.all(), request.user, label=actual_model._meta.label)
            instance = get_object_or_404(qs, pk=pk)
            return _render_combined_tab(request, instance, self.tab, menu_filter=menu_name)

    safe = _menu_tab_slug(menu_name).replace('-', '_')
    _COMenuTabView.__name__ = f'COMenu_{safe}_TabView'
    _COMenuTabView.__qualname__ = _COMenuTabView.__name__
    return _COMenuTabView


def register_combined_tabs(model_classes, label, weight):
    """
    Register a combined Custom Objects tab view for each model in the list.
    """
    for model_class in model_classes:
        # Bind model_class as a default arg so the lambda doesn't capture the loop
        # variable's final value.
        _register_tab_view(
            model_class,
            'custom_objects',
            'custom-objects',
            lambda model_class=model_class: _make_tab_view(model_class, label=label, weight=weight),
        )


# ---------------------------------------------------------------------------
# Per-menu-name related tabs
#
# A CustomObjectType with a non-empty ``menu_name`` is excluded from the combined
# tab (see ``_get_linked_custom_objects``) and surfaced in a separate tab labelled
# with the ``menu_name`` — one tab per distinct ``menu_name``.  These tabs are
# registered on built-in NetBox host models (Device, IP, …) which use NetBox's
# registry-driven tab machinery; custom-object host pages (CO→CO) render their
# combined tab via the ``custom_objects_tab_link`` template tag and keep only the
# combined tab (the exclusion still applies there).
# ---------------------------------------------------------------------------

def _distinct_menu_names():
    """Sorted list of distinct, non-empty ``menu_name`` values across all COTs.

    Returns ``[]`` if the database isn't usable yet (fresh install before
    ``migrate``) so registration is simply retried on the next process start.
    """
    from django.db.utils import OperationalError, ProgrammingError
    from netbox_custom_objects.models import CustomObjectType

    try:
        names = (
            CustomObjectType.objects
            .exclude(menu_name='')
            .values_list('menu_name', flat=True)
            .distinct()
        )
        return sorted({(n or '').strip() for n in names if (n or '').strip()})
    except (OperationalError, ProgrammingError):
        logger.warning('database unavailable — per-menu-name tabs not registered until next start')
        return []


def _menu_tab_slug(menu_name):
    from django.utils.text import slugify

    return slugify(menu_name) or 'menu'


def _make_menu_tab_view(model_class, menu_name, weight):
    """A per-menu-name combined-style tab view for one built-in host model.

    Reuses ``_render_combined_tab`` but pins ``menu_filter`` to ``menu_name`` so
    only that menu's linked objects appear.
    """

    def _badge(instance, _menu_name=menu_name):
        return _count_linked_custom_objects(instance, menu_filter=_menu_name)

    class _MenuTabView(ConditionalLoginRequiredMixin, View):
        tab = ViewTab(label=menu_name, badge=_badge, weight=weight, hide_if_empty=True)

        def get(self, request, pk, **kwargs):
            qs = _restrict_or_warn(model_class.objects.all(), request.user, label=model_class._meta.label)
            instance = get_object_or_404(qs, pk=pk)
            return _render_combined_tab(request, instance, self.tab, menu_filter=menu_name)

    safe = _menu_tab_slug(menu_name).replace('-', '_')
    _MenuTabView.__name__ = f'{model_class.__name__}Menu_{safe}_TabView'
    _MenuTabView.__qualname__ = _MenuTabView.__name__
    return _MenuTabView


def register_menu_name_tabs(model_classes, weight_base=COMBINED_WEIGHT + 10):
    """Register one per-menu-name combined-style tab per distinct ``menu_name``
    on every built-in host model that carries the combined tab.

    Idempotent (``_register_tab_view`` skips a name already present), so the
    Django autoreloader re-running registration is harmless.  Like the combined
    tab, each tab is ``hide_if_empty`` so registering broadly is cheap.
    """
    menu_names = _distinct_menu_names()
    for index, menu_name in enumerate(menu_names):
        slug = _menu_tab_slug(menu_name)
        name = f'custom_objects_menu_{slug.replace("-", "_")}'
        path = f'custom-objects-menu-{slug}'
        weight = weight_base + index
        for model_class in model_classes:
            _register_tab_view(
                model_class,
                name,
                path,
                lambda model_class=model_class, menu_name=menu_name, weight=weight: _make_menu_tab_view(
                    model_class, menu_name, weight
                ),
            )
