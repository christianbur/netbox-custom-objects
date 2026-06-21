from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_custom_objects", "0019_disable_all_bundles"),
    ]

    operations = [
        migrations.AddField(
            model_name="bundle",
            name="restart_required",
            field=models.BooleanField(default=False),
        ),
    ]
