"""Discovery, import and schema-loading for local COT bundles.

A *bundle* lives in a directory on the configured local path
(default ``/opt/netbox/local``) and is a normal Python package that bundles:

  * ``bundle.yaml`` — a manifest (``name``, optional ``verbose_name``).
  * ``schema/*.yaml`` — portable-schema COT definitions, applied via the
    existing schema executor.
  * view modules whose import registers ``COTView`` subclasses.

Discovery (filesystem scan) is always available so the Bundles page can list
bundles even when disabled.  Importing a bundle's Python and applying its
schema happens only for *enabled* bundles, during worker startup
(``CustomObjectsPluginConfig.ready()``), because views/URLs/menus freeze then.
"""

import logging
import os
import sys

from netbox.plugins import get_plugin_config

from netbox_custom_objects.constants import APP_LABEL

logger = logging.getLogger("netbox_custom_objects.cot_views")

_MANIFEST_NAME = "bundle.yaml"


def get_bundles_path():
    """Configured bundles root (default ``/opt/netbox/local``)."""
    return get_plugin_config(APP_LABEL, "bundles_path") or "/opt/netbox/local"


def _read_manifest(bundle_dir):
    import yaml

    manifest_path = os.path.join(bundle_dir, _MANIFEST_NAME)
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def discover_bundles():
    """Return ``[{name, verbose_name, package, path}]`` for every bundle.

    A bundle is a directory that contains both a ``bundle.yaml`` manifest
    and an ``__init__.py`` (so it is importable as a package).
    """
    root = get_bundles_path()
    result = []
    if not os.path.isdir(root):
        return result
    for entry in sorted(os.listdir(root)):
        bundle_dir = os.path.join(root, entry)
        if not os.path.isdir(bundle_dir):
            continue
        if not os.path.isfile(os.path.join(bundle_dir, "__init__.py")):
            continue
        manifest = _read_manifest(bundle_dir)
        if manifest is None:
            continue
        result.append(
            {
                "name": manifest.get("name") or entry,
                "verbose_name": manifest.get("verbose_name") or entry,
                "package": entry,
                "path": bundle_dir,
            }
        )
    return result


def _split_view_refs(value):
    """Normalise a schema ``views`` value (string or list) to a list of keys."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            parts.extend(_split_view_refs(item))
        return parts
    return [part.strip() for part in str(value).split(",") if part.strip()]


def package_name_prefix(package: str) -> str:
    """Underscore prefix for COT ``name`` and view keys (``security_``)."""
    return package.replace("-", "_").strip() + "_"


def package_slug_prefix(package: str) -> str:
    """Hyphen prefix for COT ``slug`` (``security-``)."""
    return package.replace("_", "-").strip() + "-"


def _prefixed_token(value: str, prefix: str) -> str:
    if not value or value.startswith(prefix):
        return value
    return prefix + value


def prefix_schema_document(doc, package: str):
    """Prefix COT names, slugs, view keys and in-document references with *package*.

    Bundle schema YAML can use short identifiers (``action``, ``rulebook``); at
    apply time they become ``security_action``, ``security-action``,
    ``security_rulebook``, etc. for package ``security``.
    """
    from netbox_custom_objects.schema.format import CUSTOM_OBJECTS_APP_LABEL_SLUG

    if not package or not isinstance(doc, dict):
        return doc
    types = doc.get("types")
    if not types:
        return doc

    name_prefix = package_name_prefix(package)
    slug_prefix = package_slug_prefix(package)
    rot_prefix = CUSTOM_OBJECTS_APP_LABEL_SLUG + "/"

    slug_map: dict[str, str] = {}
    for type_def in types:
        old_slug = (type_def.get("slug") or "").strip()
        old_name = (type_def.get("name") or "").strip()
        type_def["name"] = _prefixed_token(old_name, name_prefix)
        type_def["slug"] = _prefixed_token(old_slug, slug_prefix)
        if old_slug:
            slug_map[old_slug] = type_def["slug"]
        views = type_def.get("views")
        if views:
            type_def["views"] = ", ".join(
                _prefixed_token(part.replace("-", "_"), name_prefix)
                for part in _split_view_refs(views)
            )

    def _rewrite_related_slug(dep: str) -> str:
        dep = dep.strip()
        if not dep:
            return dep
        if dep in slug_map:
            return slug_map[dep]
        return _prefixed_token(dep, slug_prefix)

    def _rewrite_rot(rot_str: str) -> str:
        if not rot_str or not rot_str.startswith(rot_prefix):
            return rot_str
        return rot_prefix + _rewrite_related_slug(rot_str[len(rot_prefix):])

    for type_def in types:
        for field in type_def.get("fields") or []:
            rot = field.get("related_object_type")
            if rot:
                field["related_object_type"] = _rewrite_rot(rot)
            rots = field.get("related_object_types")
            if rots:
                field["related_object_types"] = [_rewrite_rot(r) for r in rots]

    return doc


def read_bundle_schema_files(bundle):
    """Read every ``schema/*.yaml`` document of ``bundle`` (read-only, no DB).

    Returns ``[{filename, types, raw, error}]`` where ``types`` is a list of
    ``{name, slug, verbose_name, description, views}`` extracted from each
    document's ``types`` list.  Parsing failures are reported per-file via
    ``error`` rather than raised, so a malformed file can't break the page.
    """
    import yaml

    schema_dir = os.path.join(bundle["path"], "schema")
    files = []
    if not os.path.isdir(schema_dir):
        return files
    for fname in sorted(os.listdir(schema_dir)):
        if not fname.endswith((".yaml", ".yml")):
            continue
        fpath = os.path.join(schema_dir, fname)
        entry = {"filename": fname, "types": [], "raw": "", "error": ""}
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                entry["raw"] = fh.read()
            doc = yaml.safe_load(entry["raw"]) or {}
        except (OSError, yaml.YAMLError) as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            files.append(entry)
            continue
        for type_def in (doc.get("types") or []) if isinstance(doc, dict) else []:
            if not isinstance(type_def, dict):
                continue
            entry["types"].append(
                {
                    "name": type_def.get("name", ""),
                    "slug": type_def.get("slug", ""),
                    "verbose_name": type_def.get("verbose_name", ""),
                    "description": type_def.get("description", ""),
                    "views": ", ".join(_split_view_refs(type_def.get("views"))),
                }
            )
        files.append(entry)
    return files


def get_bundle_views(bundle, schema_files=None):
    """COT views provided by ``bundle`` — ``[{key, label, registered}]`` (read-only).

    Combines two sources so the list works whether or not the bundle has been
    imported in this worker: COTView subclasses in the live registry whose class
    lives in the bundle package (``registered=True``), plus view keys referenced
    by the bundled schema's ``views`` fields (``registered=False`` when not yet
    loaded — e.g. the bundle is disabled or a worker restart is pending).
    """
    from netbox_custom_objects.cot_views.registry import all_cot_views

    package = bundle["package"]
    views = {}
    for key, view_cls in all_cot_views().items():
        module = getattr(view_cls, "__module__", "") or ""
        if module == package or module.startswith(package + "."):
            views[key] = {
                "key": key,
                "label": getattr(view_cls, "label", "") or key,
                "registered": True,
            }
    if schema_files is None:
        schema_files = read_bundle_schema_files(bundle)
    for schema_file in schema_files:
        for type_def in schema_file["types"]:
            for key in _split_view_refs(type_def.get("views")):
                views.setdefault(key, {"key": key, "label": key, "registered": False})
    return [views[key] for key in sorted(views)]


def get_bundle_detail(name):
    """Full read-only description of the discovered bundle ``name``.

    Returns ``{name, verbose_name, package, path, manifest, schema_files, views}``
    or ``None`` if no bundle with that name is found on the local path.  Performs
    no DB writes and does not import the bundle's Python modules.
    """
    for bundle in discover_bundles():
        if bundle["name"] != name:
            continue
        schema_files = read_bundle_schema_files(bundle)
        detail = dict(bundle)
        detail["manifest"] = _read_manifest(bundle["path"]) or {}
        detail["schema_files"] = schema_files
        detail["views"] = get_bundle_views(bundle, schema_files=schema_files)
        return detail
    return None


def _ensure_on_sys_path(root):
    if root not in sys.path:
        sys.path.insert(0, root)


def _apply_bundle_schema(bundle):
    """Load and apply every ``schema/*.yaml`` document for ``bundle`` (idempotent)."""
    import yaml

    from netbox_custom_objects.schema.executor import apply_document

    schema_dir = os.path.join(bundle["path"], "schema")
    if not os.path.isdir(schema_dir):
        return
    for fname in sorted(os.listdir(schema_dir)):
        if not fname.endswith((".yaml", ".yml")):
            continue
        with open(os.path.join(schema_dir, fname), "r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        if not doc:
            continue
        doc = prefix_schema_document(doc, bundle["package"])
        # The executor diffs against live DB state, so re-applying an unchanged
        # document on every worker start is a no-op.
        apply_document(doc, allow_destructive=False)


def load_enabled_bundles():
    """Import + schema-apply every enabled bundle.

    Called once per worker from ``ready()``.  Failures are recorded on the
    bundle's ``Bundle.last_error`` and logged, never raised, so one broken
    bundle can't take down startup.
    """
    from django.db.utils import OperationalError, ProgrammingError

    from netbox_custom_objects.models import Bundle

    app_config = __import__(
        "django.apps", fromlist=["apps"]
    ).apps.get_app_config(APP_LABEL)
    if app_config.should_skip_dynamic_model_creation():
        return

    try:
        enabled = {b.name: b for b in Bundle.objects.filter(enabled=True)}
    except (OperationalError, ProgrammingError):
        logger.warning("database unavailable — bundles not loaded until next start")
        return

    if not enabled:
        _clear_bundle_restart_flags()
        return

    root = get_bundles_path()
    _ensure_on_sys_path(root)

    for bundle in discover_bundles():
        record = enabled.get(bundle["name"])
        if record is None:
            continue
        error = ""
        try:
            __import__(bundle["package"])  # registers COTView subclasses
            _apply_bundle_schema(bundle)
            logger.info("loaded bundle %r", bundle["name"])
        except Exception as exc:  # noqa: BLE001 — never break startup
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("failed loading bundle %r", bundle["name"])
        if record.last_error != error:
            try:
                Bundle.objects.filter(pk=record.pk).update(last_error=error)
            except (OperationalError, ProgrammingError):
                pass

    _clear_bundle_restart_flags()


def _clear_bundle_restart_flags():
    from django.db.utils import OperationalError, ProgrammingError

    from netbox_custom_objects.models import Bundle

    try:
        Bundle.objects.filter(restart_required=True).update(restart_required=False)
    except (OperationalError, ProgrammingError):
        pass
