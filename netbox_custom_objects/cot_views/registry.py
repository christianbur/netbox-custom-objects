"""In-process registry of available COT views.

Populated at worker startup: built-in views import themselves, and enabled
bundles are imported during ``ready()`` (their import side effect calls
``register_cot_view``).  The registry is intentionally process-local — it is
rebuilt identically in every worker, so no cross-process state is needed.
"""

import logging

logger = logging.getLogger("netbox_custom_objects.cot_views")

# key -> COTView subclass
_REGISTRY = {}


def register_cot_view(view_cls):
    """Register a COTView subclass under its ``key``.

    Usable as a decorator.  Re-registering the same key replaces the previous
    entry (harmless on autoreload / repeat imports).
    """
    key = getattr(view_cls, "key", None)
    if not key:
        raise ValueError(f"COT view {view_cls!r} must define a non-empty 'key'.")
    _REGISTRY[key] = view_cls
    logger.debug("registered COT view %r -> %s", key, view_cls.__name__)
    return view_cls


def get_cot_view(key):
    """Return the registered COTView subclass for ``key``, or ``None``."""
    return _REGISTRY.get(key)


def all_cot_views():
    """Return a copy of the ``{key: COTView}`` registry."""
    return dict(_REGISTRY)
