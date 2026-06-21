"""Dynamic COT-views registry.

A COT view is a small, reusable presentation that any Custom Object Type can
opt into via its ``views`` field (a comma-separated list of registered view
keys).  Views are registered in-process (built-in ones plus any contributed by
enabled bundles) and rendered as related tabs on the type's objects.

The COT -> view binding is fully dynamic: nothing is keyed off a slug or
``group_name`` convention.  The registry only supplies *available* views; the
DB-stored ``CustomObjectType.views`` field decides which apply to a type.
"""

from .base import COTView
from .registry import all_cot_views, get_cot_view, register_cot_view

__all__ = (
    "COTView",
    "all_cot_views",
    "get_cot_view",
    "register_cot_view",
)
