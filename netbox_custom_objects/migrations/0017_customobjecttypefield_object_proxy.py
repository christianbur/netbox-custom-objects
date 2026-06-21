from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the plugin-only ``object_proxy`` field type to the choices of
    ``CustomObjectTypeField.type``.

    Metadata-only: ``object_proxy`` fields never produce a DB column, so this
    changes nothing at the database level.
    """

    dependencies = [
        ("netbox_custom_objects", "0016_cot_views_and_localplugin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customobjecttypefield",
            name="type",
            field=models.CharField(
                choices=[
                    ("text", "Text"),
                    ("longtext", "Text (long)"),
                    ("integer", "Integer"),
                    ("decimal", "Decimal"),
                    ("boolean", "Boolean (true/false)"),
                    ("date", "Date"),
                    ("datetime", "Date & time"),
                    ("url", "URL"),
                    ("json", "JSON"),
                    ("select", "Selection"),
                    ("multiselect", "Multiple selection"),
                    ("object", "Object"),
                    ("multiobject", "Multiple objects"),
                    ("object_proxy", "Object Proxy"),
                ],
                default="text",
                help_text="The type of data this custom object field holds",
                max_length=50,
                verbose_name="type",
            ),
        ),
    ]
