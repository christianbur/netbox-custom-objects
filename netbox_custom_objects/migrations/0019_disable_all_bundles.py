from django.db import migrations


"""One-time reset: disable every Bundle activation record.

Bundles are opt-in via the Custom Objects → Bundles UI.  Earlier dev
environments may have enabled bundles manually; this migration ensures no
bundle is auto-applied on worker startup until a user enables it again.
"""


def disable_all_bundles(apps, schema_editor):
    Bundle = apps.get_model("netbox_custom_objects", "Bundle")
    Bundle.objects.filter(enabled=True).update(enabled=False)


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_custom_objects", "0018_rename_localplugin_to_bundle"),
    ]

    operations = [
        migrations.RunPython(disable_all_bundles, migrations.RunPython.noop),
    ]
