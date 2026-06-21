# Custom Object Type enhancements: junction tables, outgoing references & per-menu navigation

> **Prototype** — based on the related-tabs branch (PR
> [#482](https://github.com/netboxlabs/netbox-custom-objects/pull/482),
> commit `0c2c5e8`), which is the build installed in the target NetBox
> environment (reported as `netboxlabs-netbox-custom-objects 0.5.1`).

## Summary (PR title + opening paragraph)

This change turns three Custom Object Type (COT) capabilities — **n:m junction
traversal**, **bidirectional/outgoing references** in the combined *Custom
Objects* tab, and **per-COT navigation menus with a matching related-tab split**
— into native model fields, forms, templates, views, navigation and API. Three
new fields are added to `CustomObjectType` (`link_table`, `menu_name`,
`metadata`) via a single migration, and the combined related-tab and navigation
machinery learn to use them. The behaviour previously existed only as a
removable runtime monkeypatch in a separate plugin; it is now implemented
properly in `netbox-custom-objects` itself.

## New model fields + migration

Added to `CustomObjectType` (`netbox_custom_objects/models.py`) and shipped in
migration **`0015_customobjecttype_cot_enhancements`** (depends on
`0014_fix_mixed_case_field_names`):

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `link_table` | `BooleanField` | `False` | GUI label *"Link table (show connected objects)"*. Marks a COT as an n:m link table so the combined tab traverses it to the far endpoint. |
| `menu_name` | `CharField(max_length=100, blank, db_index)` | `""` | If set, the COT moves to a dedicated top-level navigation menu and a separate related tab of this name. |
| `metadata` | `TextField(blank)` | `""` | Free-form YAML/JSON metadata for COT properties that have no dedicated field. Stored verbatim; never interpreted by the plugin. |

The migration is auto-detector clean: `manage.py makemigrations --check
--dry-run` reports *"No changes detected"* against the model.

## Forms & detail template

- `CustomObjectTypeForm` (`forms.py`) gains a *Behavior & navigation* fieldset
  exposing `menu_name`, `link_table` and a `metadata` textarea.
- `CustomObjectTypeBulkEditForm` gains `menu_name` and `link_table`;
  `CustomObjectTypeImportForm` gains `group_name`, `menu_name`,
  `link_table` and `metadata`.
- `customobjecttype.html` shows *Menu name*, *Link table (show connected
  objects)* and a *Metadata* panel.

## Bidirectional / outgoing references

`related_tabs/views/combined.py` — `_get_linked_custom_objects()` now appends
**outgoing** rows: for a custom-object host, the object's own OBJECT/MULTIOBJECT
field targets are surfaced in the combined tab (e.g. an Address showing the IPAM
IP it points at, not only the objects pointing at it). Each outgoing row keeps
the host as the row's object (so the row actions still target a real custom
object) and is labelled `"<field> (this object → value)"`. Implemented with a
thin `_OutgoingFieldProxy` that only overrides `__str__` and otherwise delegates
to the real field, so value resolution, batching and sorting are unchanged.

## Junction traversal

For a COT with `link_table=True` that has **exactly two** object fields,
`_transform_junctions()` rewrites each incoming link row so the **far endpoint**
becomes the primary object and the junction is demoted to a *via* reference
(`_JunctionField` carries the type label, the `via_obj`, and a Field-column
label). Rows whose far endpoint can't be resolved to a single linkable object
are left untouched, and the transform is wrapped defensively so a misconfigured
junction can never crash the page. The combined-tab template
(`related_tabs/combined/tab_partial.html`) renders these via an
`is_junction_row` branch and points the row actions at `field.via_obj` so they
target the junction object (which has a valid `custom_object_type.slug`).

## Navigation + related-tab split (`menu_name`)

- **Empty `menu_name`** (default): unchanged — the COT is listed under the stock
  *Custom Object Types* menu grouped by `group_name`, and its linked objects
  appear in the combined *Custom Objects* tab.
- **Non-empty `menu_name`**:
  - **Navigation** (`navigation.py`): the COT is removed from the stock menu
    (both `CustomObjectTypeMenuItems` and `get_grouped_menu_items` now filter on
    `menu_name`) and listed under a **new top-level menu** titled by the
    `menu_name`, still grouped internally by `group_name`. COTs sharing a
    `menu_name` collect under one menu. The extra top-level menus are registered
    once in `ready()` via `register_menu_name_menus()`.
  - **Related tab**: the COT's linked objects are **excluded** from the combined
    tab and shown in a **separate related tab** labelled with the `menu_name` —
    one tab per distinct `menu_name` — registered on built-in host models by
    `register_menu_name_tabs()`.
- **Badge counts**: the combined badge counts only empty-`menu_name` rows
  (including outgoing/junction rows); each per-menu tab counts only its own
  rows. Counts are computed from the same row list the body renders, so they can
  never disagree with what is shown.

### Multi–menu-name behaviour & edge cases

- Several distinct `menu_name`s that apply to one host produce **one separate
  tab each** (chosen over a single merged tab so each tab maps 1:1 to its
  top-level menu and label).
- Adding/removing a `menu_name` value (a brand-new top-level menu or related
  tab) requires a NetBox **restart**, because NetBox snapshots the set of
  top-level menus and the registered model-view tabs at startup. *Contents*
  update live per request, so moving a COT between existing `menu_name`s, or
  adding a COT to an existing one, shows up without a restart. This mirrors how
  a brand-new `group_name` behaves in stock NetBox.
- The combined-tab **exclusion** applies on both built-in and custom-object host
  pages. The **separate per-menu-name tab** is registered only on built-in host
  pages (Device, IP, …); custom-object host pages (CO→CO) render their combined
  tab via the `custom_objects_tab_link` template tag and keep only the combined
  tab (the exclusion still applies there).

## API

- **REST** (`api/serializers.py`): `CustomObjectTypeSerializer` exposes
  `link_table`, `menu_name` and `metadata` (read/write); `menu_name` is
  also added to `brief_fields`. drf-spectacular picks these up automatically, so
  the OpenAPI/Swagger schema includes them.
- **Filtering** (`filtersets.py`): `CustomObjectTypeFilterSet.Meta.fields` adds
  `menu_name`, `link_table` and `metadata`, so the fields are filterable
  wherever that filterset is used (UI list views and the object selector).
- **GraphQL**: the plugin's GraphQL layer exposes only the *dynamic per-COT
  object models* (`Table<id>Model`), not the `CustomObjectType` metamodel — there
  is no `CustomObjectType` GraphQL type to extend, so no GraphQL change is
  required for these fields. (NetBox core does not auto-expose plugin metamodels
  in GraphQL.)
- **Derived data deliberately *not* added to the API**: the junction
  far-endpoints and bidirectional/outgoing links are a *presentation-layer* view
  computed for the combined tab. The underlying relationships are already fully
  queryable through the existing per-object REST/GraphQL fields and the
  `LinkedObjectsView` (`/linked-objects/`) endpoint, so re-exposing the derived
  tab rows as a separate API surface would duplicate existing data. The three
  new stored fields are fully readable/writable via REST as described above.

## Field-group section order follows display weight (issue #577)

Previously a COT's field **sections** were ordered **alphabetically by group
name**: every view built its `field_groups` mapping from a queryset ordered
`("group_name", "weight", "name")` and accumulated fields into a dict keyed by
group name, so display weight could only reorder fields *within* a section, not
the sections themselves. Ungrouped fields all collapsed to the front (the empty
`group_name` sorts first), so a group could never sit *between* two ungrouped
fields.

The fix orders sections by **display weight** instead. `views.py` gains
`build_field_groups_by_weight()` / `_append_field_group_entry()`: fields are
walked in global `(weight, name)` order, each group accumulates into a single
section anchored at its **lowest-weight (first-seen) member** and stays
contiguous, and each ungrouped field becomes its own single-entry section so
ungrouped fields **interleave** with groups by weight. The grouping structure
changed from a `dict` to an ordered `list` of `[group_name, [fields]]` sections
(so repeated ungrouped runs can interleave); the COT-type detail, custom-object
detail and edit-form builder all use it, and the four consuming templates
(`customobjecttype.html`, `customobject.html` ×2, `inc/edit_fields.html`) now
iterate the list directly instead of `.items`.

Example (weights in parentheses) — the section order now matches the field
weights rather than A–Z group names:

```
Index (10)              # ungrouped
Name (20)               # ungrouped
Source            -> Zone (30), Address (40)
Destination       -> Zone (50), Address (60)
Service & App     -> Service (70), App (80)
Action            -> Action (90)
Comment (100)           # ungrouped
```

Weight-based ordering is the prototype default (no config toggle). If upstream
wants this configurable, a per-COT or plugin-setting flag could switch
`build_field_groups_by_weight()` back to the legacy alphabetical grouping; that
is left as a follow-up and intentionally not built here.

## Verification performed

- `python -m py_compile` on every changed Python file — clean.
- `manage.py makemigrations netbox_custom_objects --check --dry-run` inside the
  target NetBox (patched package on `PYTHONPATH`) — *"No changes detected"*
  (migration 0015 fully covers the model changes) and all changed modules import
  cleanly inside real NetBox.
- Added best-effort API/filterset tests in `tests/test_api.py`
  (`test_cot_enhancement_fields_*`).

### Still requires a running install to verify

Full runtime behaviour — especially the new top-level navigation menus, the
per-menu-name related tabs, junction rendering and badge counts — requires
installing the patched package and running the migration:

```
manage.py migrate netbox_custom_objects
# then restart NetBox (registers the new menus/tabs at startup)
```

## Portable-schema round-trip for the new COT attributes

The three new COT attributes (`link_table`, `menu_name`, `metadata`) are
first-class in the portable-schema layer so export/import is lossless:

- `schema/cot_schema_v1.json` — declared in `cot_definition.properties`
  (`additionalProperties: false`, so they must be listed).
- `schema/format.py` — `COT_ATTR_DEFAULTS` (`link_table=False`, `menu_name=""`,
  `metadata=""`).
- `schema/exporter.py` — `export_cot()` emits them, eliding values equal to the
  default; `metadata` is emitted as a raw string (no reparse).
- `schema/comparator.py` — included in the COT-level diff.
- `schema/executor.py` — applied on create and update.

Verified by `tests/schema/test_exporter.py` and
`tests/schema/test_executor.py` (`ExecutorEnhancementAttrsRoundTripTestCase`):
`Ran 14 tests ... OK` (create + update round-trip, default eliding,
`link_table=False` produces no diff).

## Portable-schema UI tabs (export + define via text)

Two UI surfaces sit on top of the existing portable-schema backend
(`schema/exporter.py`, `schema/comparator.py`, `schema/executor.py`,
`schema/cot_schema_v1.json`). No schema logic is reimplemented — the views only
translate between text (JSON/YAML) and the backend's document dict, validate and
render.

### "Export" tab (COT *detail* page)

- `views.CustomObjectTypeSchemaView` — a read-only `generic.ObjectView`
  registered with `@register_model_view(CustomObjectType, 'schema',
  path='schema')` and a `ViewTab(label="Export", weight=560)`, so it appears as a
  detail tab exactly like the existing *Fields* tab.
- Renders the COT's portable-schema document via
  `schema.exporter.export_cots([cot])` (a complete, re-importable
  `{schema_version, types:[…]}` document) in **both YAML and JSON**. YAML is the
  default tab when `pyyaml` is installed, otherwise JSON; JSON is always
  available. Each rendering has a one-click **Copy** affordance.
- Template: `templates/netbox_custom_objects/customobjecttype_schema.html`.

### "JSON import" screen (reachable from the COT list/add flow)

- `views.CustomObjectTypeDefineView` — registered with
  `@register_model_view(CustomObjectType, 'define', path='define',
  detail=False)` (URL `customobjecttype_define`). A **"JSON import"** button
  next to *Add* on the *Custom Object Types* navigation item links to it.
- The user pastes a portable-schema document (JSON **or** YAML; parsing tries
  JSON first, then YAML). **Preview** validates against `cot_schema_v1.json`
  (via the shared `schema.validation` helper) and shows the comparator diff
  (`schema.comparator.diff_document`) — per-type create/update/no-change badges,
  add/alter/remove counts, COT-level attribute changes and warnings — without
  touching the DB. **Apply** runs the document through
  `schema.executor.apply_document` (honouring an *Allow destructive changes*
  checkbox) to create/update the COT(s), surfacing parse / validation /
  destructive / unresolvable-reference errors cleanly. Apply requires both the
  `add` and `change` permissions on `CustomObjectType`. UX mirrors the NSM
  "define via text" screen.
- Template: `templates/netbox_custom_objects/customobjecttype_define.html`.

### Shared validation helper

`schema/validation.py` centralises loading and validating against
`cot_schema_v1.json` (`get_validator` / `iter_schema_errors` /
`schema_error_dicts`). The REST API (`api/views.py`) and the new UI view both
use it, removing the duplicated validator that previously lived only in the API.

### Verification

Runtime-verified in the `netbox-dev` container against the clone on
`PYTHONPATH` (test DB has migration 0015 applied):

- New UI tests `tests/test_schema_ui.py` (export tab renders the document text
  for a COT with `link_table`/`menu_name`/`metadata` set; define-via-text
  preview shows the diff without applying; schema-validation-error and
  parse-error cases; apply creates the COT from pasted JSON and YAML):
  `Ran 8 tests ... OK`.
- Regression run of the schema + navigation suites (covers the `api/views.py`
  validation refactor and the `navigation.py` button):
  `netbox_custom_objects.tests.schema.test_schema_api`,
  `test_exporter`, `test_executor` and `tests.test_navigation` —
  `Ran 140 tests ... OK`.
