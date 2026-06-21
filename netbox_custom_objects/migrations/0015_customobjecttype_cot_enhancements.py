from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_custom_objects", "0014_fix_mixed_case_field_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="customobjecttype",
            name="menu_name",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "If set, list this Custom Object Type under a dedicated top-level "
                    "navigation menu of this name (instead of the Custom Objects menu), and "
                    "show its linked objects in a separate related tab of this name. Custom "
                    "Object Types that share a menu name are collected under the same menu. "
                    "Changing this value only takes effect after the NetBox workers are "
                    "restarted, because the navigation menu and related tab are registered "
                    "at worker startup."
                ),
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="customobjecttype",
            name="link_table",
            field=models.BooleanField(
                default=False,
                verbose_name="Link table (show connected objects)",
                help_text=(
                    "Treat this Custom Object Type as an n:m link table. When enabled and "
                    "the type has exactly two object fields, the combined Custom Objects tab "
                    "shows the far endpoint of each link as the primary object, with the link "
                    'table row itself surfaced as a "via" reference.'
                ),
            ),
        ),
        migrations.AddField(
            model_name="customobjecttype",
            name="metadata",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Free-form YAML or JSON metadata for Custom Object Type properties that "
                    "have no dedicated field. Stored as-is; not interpreted by the plugin."
                ),
            ),
        ),
    ]
