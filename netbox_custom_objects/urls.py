from django.urls import include, path
from utilities.urls import get_model_urls

from . import views
from .constants import APP_LABEL
from .cot_views.views import CustomObjectCOTView
from .cot_views.bundle_views import (
    BundleListView,
    BundleToggleView,
    BundleView,  # noqa: F401 — import registers the detail model view
)
from .group_views import CustomObjectTypeGroupListView

app_name = APP_LABEL

urlpatterns = [
    path('custom-object-types/', include(get_model_urls(APP_LABEL, 'customobjecttype', detail=False))),
    path('custom-object-types/<int:pk>/', include(get_model_urls(APP_LABEL, 'customobjecttype'))),

    # Custom Object Type Fields
    path(
        "custom-object-type-fields/<int:pk>/",
        include(get_model_urls(APP_LABEL, "customobjecttypefield")),
    ),
    path(
        "custom-object-type-fields/add/",
        views.CustomObjectTypeFieldEditView.as_view(),
        name="customobjecttypefield_add",
    ),

    # Journal Entries (must come before custom object patterns)
    path(
        "journal-entries/add/",
        views.CustomJournalEntryEditView.as_view(),
        name="custom_journalentry_add",
    ),

    # COT group summary pages (menu_name + group_name; before catch-all routes).
    path(
        "groups/<str:menu_name>/<str:group_name>/",
        CustomObjectTypeGroupListView.as_view(),
        name="customobjecttype_group_list",
    ),

    # Bundles (must come before the <str:custom_object_type> catch-all).
    path(
        "bundles/",
        BundleListView.as_view(),
        name="bundle_list",
    ),
    path(
        "bundles/<str:name>/toggle/",
        BundleToggleView.as_view(),
        name="bundle_toggle",
    ),
    # Detail view (registered via @register_model_view(Bundle)).
    path(
        "bundles/<int:pk>/",
        include(get_model_urls(APP_LABEL, "bundle")),
    ),

    # Custom Objects
    path(
        "<str:custom_object_type>/",
        views.CustomObjectListView.as_view(),
        name="customobject_list",
    ),
    path(
        "<str:custom_object_type>/add/",
        views.CustomObjectEditView.as_view(),
        name="customobject_add",
    ),
    path(
        "<str:custom_object_type>/bulk-edit/",
        views.CustomObjectBulkEditView.as_view(),
        name="customobject_bulk_edit",
    ),
    path(
        "<str:custom_object_type>/bulk-delete/",
        views.CustomObjectBulkDeleteView.as_view(),
        name="customobject_bulk_delete",
    ),
    path(
        "<str:custom_object_type>/bulk-import/",
        views.CustomObjectBulkImportView.as_view(),
        name="customobject_bulk_import",
    ),
    path(
        "<str:custom_object_type>/<int:pk>/",
        views.CustomObjectView.as_view(),
        name="customobject",
    ),
    path(
        "<str:custom_object_type>/<int:pk>/edit/",
        views.CustomObjectEditView.as_view(),
        name="customobject_edit",
    ),
    path(
        "<str:custom_object_type>/<int:pk>/delete/",
        views.CustomObjectDeleteView.as_view(),
        name="customobject_delete",
    ),
    path(
        "<str:custom_object_type>/<int:pk>/journal/",
        views.CustomObjectJournalView.as_view(),
        name="customobject_journal",
    ),
    path(
        "<str:custom_object_type>/<int:pk>/changelog/",
        views.CustomObjectChangeLogView.as_view(),
        name="customobject_changelog",
    ),
    path(
        "<str:custom_object_type>/<int:pk>/contacts/",
        views.CustomObjectContactsView.as_view(),
        name="customobject_contacts",
    ),
    # Single COT-agnostic route for any registered COT view (see cot_views).
    path(
        "<str:custom_object_type>/<int:pk>/view/<str:view_key>/",
        CustomObjectCOTView.as_view(),
        name="customobject_cot_view",
    ),
]
