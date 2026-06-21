# netbox-custom-objects (prototype)

> **Technology prototype — no warranty**
>
> This repository is **not** an official [NetBox Labs](https://github.com/netboxlabs/netbox-custom-objects) release.
> It is a **technology prototype** that demonstrates ideas for extending the Custom Objects plugin
> (COT metadata, Related Tabs, portable schema UI, **COT Views**, **local bundles**).
>
> It is **not** maintained as error-free or production-ready, makes **no claim** to completeness
> or stability, and **must not** be adopted as-is into NetBox Labs or production. Use at your own risk.
>
> **Example bundles** (Security, IPAM tree, Cisco demos) live in a companion repository:
> [github.com/christianbur/netbox-custom-objects-bundels](https://github.com/christianbur/netbox-custom-objects-bundels)

---

## What this prototype demonstrates

Built on a NetBox Labs baseline (Custom Objects with Related Tabs), this fork adds:

| Area | Summary |
|------|---------|
| **COT metadata** | Fields `link_table`, `menu_name`, `metadata` on Custom Object Type |
| **Related Tabs** | Outgoing references, n:m junction traversal, separate tabs per `menu_name` |
| **Field groups** | Sections ordered by display weight instead of alphabetical group name |
| **Portable schema UI** | Export tab and define-via-text (JSON/YAML) in the plugin admin |
| **COT Views** | Registerable extra tabs / proxy list pages per COT (`views` field) |
| **Local bundles** | Drop-in packages under `bundles_path` (default `/opt/netbox/local`) with GUI enable/disable |
| **`object_proxy`** | Field type: list page shows instances of a referenced type |
| **Branching** | Extra hooks when `netbox_branching` is installed |

Detailed design notes:

- [`PROTOTYPE_COT_ENHANCEMENTS.md`](PROTOTYPE_COT_ENHANCEMENTS.md) — COT fields, Related Tabs, navigation, schema UI
- [`docs/bundle-validation-plan.md`](docs/bundle-validation-plan.md) — validation strategy for bundle schemas
- [`FEATURE_REQUEST_COT_VIEWS_AND_BUNDLES.md`](FEATURE_REQUEST_COT_VIEWS_AND_BUNDLES.md) — draft feature request for NetBox Labs

### n:m link tables (`link_table`) — in plain terms

**Many-to-many (n:m)** means many objects on side A can relate to many on side B — e.g. many devices linked to many security zones.

In Custom Objects this is usually a **junction COT**: a dedicated type whose **rows are links**, with **two object fields** (one endpoint each).

**Example** ([`security-object-link`](https://github.com/christianbur/netbox-custom-objects-bundels/blob/main/security/schema/security_objects.yaml)):

- Field `netbox_object` → device, prefix, interface, …
- Field `policy_object` → zone, address, service, …

Without `link_table`, the *Custom Objects* tab on a device lists the **link rows** themselves.
With `link_table: true`, the tab **traverses the junction** and shows the **far endpoint** (the zone or address you care about), with the link as secondary *via* context.

---

## Example bundles

Working demos use bundles from the companion repo:

```bash
git clone https://github.com/christianbur/netbox-custom-objects-bundels.git /opt/netbox/local
```

Includes `security/` (policy COTs, rulebook / matrix / IP-analyzer views), `ipam_tree/`, and `cisco_*` schema demos.

After cloning: enable bundles under **Plugins → Custom Objects → Bundles**, then **restart NetBox workers** (views and URLs register at startup).

---

## Installation (prototype)

**Do not** use `pip install netboxlabs-netbox-custom-objects` — this fork diverges from upstream.

```bash
git clone https://github.com/christianbur/netbox-custom-objects.git
cd netbox-custom-objects
pip install -e .
```

`configuration.py`:

```python
PLUGINS = [
    # ...
    "netbox_custom_objects",
]

PLUGINS_CONFIG = {
    "netbox_custom_objects": {
        "bundles_path": "/opt/netbox/local",
    },
}
```

`PYTHONPATH` must include the bundle root (e.g. `/opt/netbox/local`) so bundle packages such as `security` are importable.

```bash
./manage.py migrate netbox_custom_objects
# Restart NetBox + workers
```

---

## Migrations (0015–0020)

Adds `link_table` / `menu_name` / `metadata`, COT `views`, `Bundle` model, and `object_proxy` field type. Run `migrate` after every pull.

---

## Upstream

Production documentation and releases:

- [netboxlabs/netbox-custom-objects](https://github.com/netboxlabs/netbox-custom-objects)
- [docs/index.md](docs/index.md) (partially still upstream text; prototype-specific parts are documented above)

---

## License

Same as upstream — see [`LICENSE.md`](LICENSE.md).
