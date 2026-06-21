# Bundle Validation Plan — Express Cisco Data-Model Dependencies with Existing Validators

## Guiding principle

**No new validators, no custom constraint engine.** We only use validation
mechanisms that already exist in the portable COT schema and in NetBox. Anything
that cannot be expressed with an existing validator is *not enforced* — at most it
is documented as free-form YAML in the COT `metadata` field.

This explicitly drops the previously considered constraint DSL/engine
(`required_if`, `mutually_exclusive`, `required_together`, `unique_together`,
`min_items`/`max_items`, `same_parent` referential consistency). None of those
are built.

## What the existing validators already cover

Documented in `docs/portable-schema.md` and implemented in
`schema/format.py` / `schema/cot_schema_v1.json`:

- `validation_minimum` / `validation_maximum` — integer / decimal ranges
  (e.g. VLAN ID 2–4093, ACI Pod ID 1–255, Node ID 101–4000, BGP AS number).
- `validation_regex` — text / longtext pattern checks.
- `required` — mandatory fields.
- `unique` — single-field uniqueness.
- `default` — default values.
- `select` / `multiselect` with `choice_set` — enumerations (closed value sets).
- `object` / `multiobject` references with `related_object_type(s)`,
  `is_polymorphic`, `related_object_filter`, `on_delete_behavior` — referential
  links (FK existence, optional static filter, delete behavior).

These map directly onto most per-attribute constraints in the netascode Cisco
data models (ranges, patterns, required flags, enums, references).

## Cisco data-model dependencies that existing validators CANNOT express

These remain **unenforced** (documented only, if at all, in `metadata`):

- Conditional dependencies (field X required/allowed only if field Y = value).
- Mutual exclusion (exactly-one / at-most-one of a field group).
- Co-required field groups (e.g. `source_from_port` + `source_to_port`).
- Composite / scoped uniqueness (e.g. name unique per tenant, node ID per fabric).
- List cardinality (min/max items on a `multiobject` field).
- Cross-object referential consistency beyond FK existence
  (e.g. an EPG's bridge domain must belong to the same tenant as the EPG).
- Aggregate / scale limits (e.g. max N bridge domains per tenant).

## Scope

### In scope

1. **Map every expressible constraint** in the Cisco bundles onto existing
   per-field validators: integer `validation_minimum`/`validation_maximum`,
   `validation_regex`, `required`, `unique`, `default`.
2. **Enums via the existing `select` validator.** Today the Cisco bundles use
   `text` + an "Allowed values: …" hint in `description`, because
   `select`/`multiselect` require a pre-existing `CustomFieldChoiceSet`
   (`UnknownChoiceSetError` in `schema/executor.py`). To deliver the existing
   `select` validator self-contained in a drop-in bundle, ship choice sets in the
   schema document and provision them idempotently before apply.
   - Add an optional top-level `choice_sets:` to the schema document
     (`schema/cot_schema_v1.json`, `schema/format.py`).
   - `provision_choice_sets(doc)` using
     `CustomFieldChoiceSet.objects.get_or_create(...)`, called in
     `schema/executor.py::apply_document` before `diff_document` so all paths
     (UI / API / bundle) benefit.
   - Round-trip in `schema/exporter.py`.
   - This is *infrastructure to deliver an existing validator*, not a new
     validator.

### Decision points (deferred / pending user confirmation)

- **Choice-set delivery:** ship `choice_sets:` in the bundle (recommended) vs.
  keep `text` + description vs. pre-create choice sets manually/migration.
- **API enforcement gap:** existing per-field validators (`validation_regex`,
  `validation_minimum`/`validation_maximum`) are applied **only in the UI form**
  (`field_types.py` `get_form_field`), not on the model field or serializer, so
  REST-API / programmatic writes bypass them. The value check already exists
  centrally in `CustomObjectTypeField.validate()` (`models.py`) but is not called
  on instance save. Optionally wire that existing `validate()` into save so the
  existing validators also apply via API — no new validator, just wiring.

### Out of scope

- Any custom constraint engine or new constraint schema/DSL.
- Conditional, mutual-exclusion, co-required, composite-unique, cardinality, and
  referential-consistency enforcement (documented in `metadata` only, never
  enforced).

## Related gap (observed, optional)

The schema executor does **not** enforce `RESERVED_FIELD_NAMES`
(`constants.py`) — only the UI form does. A reserved name such as `tags` applied
via a bundle is created and then collides at runtime. Same pattern as the
per-field validators. Optionally add a reserved-name check in
`schema/executor.py::_schema_def_to_field_kwargs` (or in the bundle loader).

## Bundle naming convention

All Cisco bundle packages are prefixed with `cisco_` for consistency. The
displayed `verbose_name` stays human-readable (e.g. "Cisco ACI").

### COT name/slug schema (netascode bundles)

One data model = one naming scheme — **no curated short names alongside
path-based generator names**. Every COT in `cisco_aci`, `cisco_meraki`, and
`cisco_catalyst_center` follows:

| Field | Pattern | Example |
|-------|---------|---------|
| `name` | `cisco_<produkt>_<pfad>` (underscores) | `cisco_aci_tenants_bridge_domains` |
| `slug` | `cisco-<produkt>-<pfad>` (hyphens, max 100) | `cisco-aci-tenants-bridge-domains` |

Products: `aci`, `meraki`, `cc` (Catalyst Center → prefix `cisco_cc_` /
`cisco-cc-`). Slugs derive from the netascode schema path; when a path exceeds
100 characters the generator truncates and appends a hash suffix for uniqueness.
YAML schema files are the source of truth; the DB must not retain legacy
short slugs such as `cisco-aci-tenant` or `cisco-cc-area`.

- `local/aci/` -> `local/cisco_aci/` (`bundle.yaml` `name: cisco_aci`)
- `local/meraki/` -> `local/cisco_meraki/` (`name: cisco_meraki`)
- Future: `cisco_catalyst_center`, `cisco_ndo`, `cisco_vxlan`, `cisco_sdwan`,
  `cisco_ise`, `cisco_fmc`, `cisco_nxos`, `cisco_iosxe`.
- Non-Cisco bundles (`nsm`, `ipam_tree`) keep their current names.

Renaming an existing, activated bundle requires: move the folder, update
`bundle.yaml` `name:`, rename/re-create the DB `Bundle` record (enabled), and
restart the worker so discovery + menu re-register.

**Status: implemented for `aci` -> `cisco_aci` and `meraki` -> `cisco_meraki`.**
Both folders were moved, `bundle.yaml` `name:` updated, and the existing
`Bundle` records renamed in place via `Bundle.objects.filter(name=...).update(name=...)`
(the record is bound to the bundle solely by its unique `name` field, so a field
rename keeps `enabled=True` and leaves the already-applied COTs untouched — no
duplicates). Verified live: Bundles page shows package `cisco_aci`/`cisco_meraki`
with `last_error` empty, discovery lists no orphan `aci`/`meraki`, and the COT
counts are unchanged.

## Apply to the Cisco bundles

For `local/aci/`, `local/meraki/`, and the remaining bundles
(catalyst_center, NDO, VXLAN, SD-WAN, ISE, FMC, NX-OS, IOS-XE):

- Convert `text` + "Allowed values: …" enums to real `select` fields with shipped
  `choice_sets:` (e.g. `aci-node.role`, `aci-filter-entry.ethertype`/`ip_protocol`,
  `aci-contract.scope`).
- Ensure numeric ranges use `validation_minimum`/`validation_maximum`, patterns
  use `validation_regex`, mandatory fields use `required`, and identity fields
  use `unique` where a single-field constraint suffices.
- Record any non-expressible dependency (conditional, composite-unique,
  cardinality, referential) as documentation in the COT `metadata` field — not
  enforced.

## Verification (shared `netbox-dev` container, run serially)

- If `choice_sets:` provisioning is adopted: choice sets are created idempotently
  (second apply produces no duplicates); `select` fields show options in UI + API.
- Bundles load without error (`Bundle.last_error` empty); existing bundles
  (`nsm`, `ipam_tree`, `aci`, `meraki`) remain green.
- Existing per-field validators behave as today (UI), and — if the API gap is
  closed — also reject invalid values via REST API.
