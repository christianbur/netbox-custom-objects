# ✨ Feature Request — Copy/paste for GitHub

**Repository:** [netboxlabs/netbox-custom-objects](https://github.com/netboxlabs/netbox-custom-objects/issues/new?template=01-feature_request.yaml)

---

## Add a title*

**Extensible COT metadata, COT Views, and optional filesystem bundles for drop-in extensions**

---

## Plugin Version*

`0.5.1` (NetBox Labs GA baseline) — the ideas below are demonstrated in a **technology prototype**, not in an official Labs release:

- Plugin fork: [christianbur/netbox-custom-objects](https://github.com/christianbur/netbox-custom-objects)
- Example bundles: [christianbur/netbox-custom-objects-bundels](https://github.com/christianbur/netbox-custom-objects-bundels)

> The prototype is **not** production-ready and makes **no claim** to being error-free. It exists to show what an extension could look like in a running NetBox dev setup.

---

## Proposed functionality*

Today, Custom Object Types (COTs) are powerful for no-code data modelling, but **behaviour beyond fields and the combined Related tab** still requires a full NetBox plugin (Python package, releases, maintenance). I propose three complementary layers:

### 1. First-class COT metadata (model fields)

Add optional attributes on `CustomObjectType` (portable-schema round-trip included):

| Field | Purpose |
|-------|---------|
| `link_table` | Mark a many-to-many **junction** COT (see below); the combined Related tab traverses to the *far* endpoint |
| `menu_name` | Move a COT to its own top-level menu + separate Related tab (instead of only `group_name`) |
| `metadata` | Opaque YAML/JSON for integrators (plugin does not interpret it; bundles/apps do) |

**Demo:** Security policy COTs store `nsm_config` in `metadata` — see bundle [`security/schema/`](https://github.com/christianbur/netbox-custom-objects-bundels/tree/main/security/schema).

### 2. Richer Related tab (presentation only)

Extend the existing combined *Custom Objects* tab without new API surface:

- **Outgoing references** — show OBJECT/MULTIOBJECT targets *from* the host object (not only incoming links)
- **Junction traversal (`link_table`)** — see next subsection

#### n:m link tables — what `link_table` means

**Many-to-many (n:m)** means many objects on side A can relate to many on side B (e.g. many devices ↔ many security zones). In Custom Objects this is usually a **junction COT**: a dedicated type whose rows are links, with **two object fields** (one per endpoint).

**Demo:** [`security-object-link`](https://github.com/christianbur/netbox-custom-objects-bundels/blob/main/security/schema/security_objects.yaml) connects a NetBox object (`netbox_object`: device, prefix, …) to a policy object (`policy_object`: zone, address, …).

| Without `link_table` | With `link_table: true` |
|----------------------|-------------------------|
| Device detail → *Custom Objects* lists **link rows** (“Object Link router1 → Zone DMZ”) | Same tab lists **Zone DMZ**, **Address Web**, … with the link as *via* context |

So n:m relationships read naturally in the UI instead of exposing internal junction records as the primary row.

### 3. COT Views (registered tab / proxy list per COT)

- New COT field: `views` — comma-separated keys of registered **COTView** handlers
- A COTView adds a related tab (or collection proxy page) with custom template/context — e.g. rulebook table, zone matrix, IP tree
- Views register at worker startup (same lifecycle as NetBox model views)

**Demo:** [`security/views/rulebook.py`](https://github.com/christianbur/netbox-custom-objects-bundels/blob/main/security/views/rulebook.py) — full rulebook grid with row grouping and IP Analyzer applet.

### 4. Optional filesystem bundles (integrator path, not a replacement for plugins)

- Config key `bundles_path` (default e.g. `/opt/netbox/local`)
- Each bundle: `bundle.yaml` + `schema/*.yaml` + Python package that registers COTViews
- GUI: enable/disable bundles; schema apply on startup for enabled bundles
- **Important:** bundles are for **drop-in lab/integrator demos**, not a substitute for signed, versioned PyPI plugins

**Demo bundles** (clone → mount at `bundles_path`):

| Bundle | What it demonstrates |
|--------|----------------------|
| [`security/`](https://github.com/christianbur/netbox-custom-objects-bundels/tree/main/security) | Policy objects, rulebook/matrix/IP-analyzer views |
| [`ipam_tree/`](https://github.com/christianbur/netbox-custom-objects-bundels/tree/main/ipam_tree) | Custom COT view over IPAM data |
| [`cisco_*`](https://github.com/christianbur/netbox-custom-objects-bundels) | Portable-schema bundle pattern for vendor models |

### 5. Smaller UX improvements (optional, shown in prototype)

- **`object_proxy` field type** — COT list page shows instances of a referenced type (virtual rulebook pattern)
- **Field sections ordered by display weight** instead of alphabetical group name ([#577](https://github.com/netboxlabs/netbox-custom-objects/issues/577))
- **Portable schema UI** — Export tab + define-via-text on the COT admin pages

Technical notes in the prototype: [`PROTOTYPE_COT_ENHANCEMENTS.md`](https://github.com/christianbur/netbox-custom-objects/blob/main/PROTOTYPE_COT_ENHANCEMENTS.md)

---

## Use case*

**Problem:** Teams want Custom Objects to feel like first-class NetBox modules (dedicated menus, specialised list views, vendor-specific object sets) without every integrator shipping and maintaining a separate Django plugin.

**Who benefits:**

- **Network / security teams** — rulebooks, policy matrices, and analysis views bound to COTs they define in YAML
- **Integrators / vendors** — ship a schema + view package as a bundle for PoC/lab; graduate to a real plugin only when needed
- **Power users** — `metadata` + COT views cover workflows that today need monkey-patches or external plugins

**Concrete demo workflow:**

1. Install prototype plugin + clone [bundels repo](https://github.com/christianbur/netbox-custom-objects-bundels) to `/opt/netbox/local`
2. Enable **Security** bundle → COTs + rulebook view appear
3. Open `security-rulebook` → **Rulebook** tab shows policy rules with grouping, filters, IP analysis

This addresses the gap between “tags/custom fields” (too limited) and “full plugin” (too heavy) for many domain-specific UIs on top of Custom Objects.

---

## External dependencies

**Proposed upstream feature:** ideally **no new runtime dependencies** beyond what Custom Objects already uses (`pyyaml` where schema UI exists today).

The **demo bundles** may pull in additional Python code vendored inside the bundle package (prototype `security/` bundle vendors analysis/rulebook helpers). That code would **not** ship with netbox-custom-objects itself — only the **bundle loader + COT view registry** would.

No new external services. Bundle filesystem access is local only (`bundles_path`).

---

## Links (summary)

| Resource | URL |
|----------|-----|
| Prototype plugin | https://github.com/christianbur/netbox-custom-objects |
| Example bundles | https://github.com/christianbur/netbox-custom-objects-bundels |
| Design notes | https://github.com/christianbur/netbox-custom-objects/blob/main/PROTOTYPE_COT_ENHANCEMENTS.md |
| Security bundle README | https://github.com/christianbur/netbox-custom-objects-bundels/blob/main/README.md |
