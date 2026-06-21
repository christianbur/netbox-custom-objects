# netbox-custom-objects (Prototyp)

> **Technologie-Prototyp — ohne Gewähr**
>
> Dieses Repository ist **kein** offizielles [NetBox Labs](https://github.com/netboxlabs/netbox-custom-objects)-Release.
> Es ist ein **Technologie-Prototyp**, der Ideen für Erweiterungen des Custom-Objects-Plugins
> demonstrieren soll (COT-Metadaten, Related Tabs, portable Schema-UI, **COT Views**, **Local Bundles**).
>
> Es wird **nicht** fehlerfrei betrieben, **legt keinen Anspruch** auf Vollständigkeit,
> Stabilität oder Produktionsreife und soll **so nicht** in NetBox Labs oder produktiv
> übernommen werden. Nutzung auf eigenes Risiko.
>
> **Beispiel-Bundles** (Security, IPAM Tree, Cisco-Demos) liegen in einem separaten Repo:
> [github.com/christianbur/netbox-custom-objects-bundels](https://github.com/christianbur/netbox-custom-objects-bundels)

---

## Was dieser Prototyp zeigt

Auf Basis eines NetBox-Labs-Standes (Custom Objects mit Related Tabs) erweitert der Fork
u. a.:

| Bereich | Kurzbeschreibung |
|---------|------------------|
| **COT-Metadaten** | Felder `link_table`, `menu_name`, `metadata` am Custom Object Type |
| **Related Tabs** | Outgoing-Referenzen, Junction-Tabellen-Traversal, getrennte Tabs pro `menu_name` |
| **Feldgruppen** | Sections nach Display-Weight statt alphabetisch nach Gruppenname |
| **Portable Schema UI** | Export-Tab und Define-via-Text (JSON/YAML) im Plugin |
| **COT Views** | Registrierbare Zusatz-Tabs/Proxy-Listen pro COT (`views`-Feld) |
| **Local Bundles** | Drop-in-Pakete unter `bundles_path` (Default `/opt/netbox/local`) mit GUI-Aktivierung |
| **`object_proxy`** | COT-Feldtyp: Listenseite zeigt Instanzen eines referenzierten Typs |
| **Branching** | Zusätzliche Hooks, wenn `netbox_branching` installiert ist |

Ausführliche technische Notizen:

- [`PROTOTYPE_COT_ENHANCEMENTS.md`](PROTOTYPE_COT_ENHANCEMENTS.md) — COT-Felder, Related Tabs, Navigation, Schema-UI
- [`docs/bundle-validation-plan.md`](docs/bundle-validation-plan.md) — Validierungsstrategie für Bundle-Schemas

## Beispiel-Bundles

Die lauffähigen Demos binden **Bundles** aus dem Companion-Repo ein:

```bash
git clone https://github.com/christianbur/netbox-custom-objects-bundels.git /opt/netbox/local
```

Dort u. a. `security/` (Policy-COTs, Rulebook-, Matrix- und IP-Analyzer-Views),
`ipam_tree/`, `cisco_aci/`, `cisco_catalyst_center/`, `cisco_meraki/`.

Nach dem Klon: Bundles in NetBox unter **Plugins → Custom Objects → Bundles** aktivieren,
Worker **neu starten**.

## Installation (Prototyp)

**Nicht** `pip install netboxlabs-netbox-custom-objects` — dieser Fork weicht upstream ab.

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

`PYTHONPATH` muss das Bundle-Root enthalten (z. B. `/opt/netbox/local`), damit Bundle-Pakete
importierbar sind.

```bash
./manage.py migrate netbox_custom_objects
# NetBox + Worker neu starten
```

## Migrations (0015–0020)

Neue Migrationen u. a. für `link_table` / `menu_name` / `metadata`, COT-`views`, Model
`Bundle`, Feldtyp `object_proxy`. Nach Pull immer `migrate` ausführen.

## Upstream

Ursprung und produktionsreife Dokumentation:

- [netboxlabs/netbox-custom-objects](https://github.com/netboxlabs/netbox-custom-objects)
- [docs/index.md](docs/index.md) (teilweise noch Labs-Text; Prototyp-Teile siehe oben)

## Lizenz

Wie upstream — siehe [`LICENSE.md`](LICENSE.md).
