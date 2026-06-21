from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_custom_objects", "0015_customobjecttype_cot_enhancements"),
    ]

    operations = [
        migrations.AddField(
            model_name="customobjecttype",
            name="views",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "Comma-separated keys of registered COT views to expose as related "
                    "tabs on this type's objects. The available keys come from the COT "
                    "views registry (built-in plus enabled local plugins). A newly "
                    "registered view only becomes selectable after the NetBox workers "
                    "are restarted, because the registry is populated at worker startup."
                ),
                max_length=500,
            ),
        ),
        migrations.CreateModel(
            name="LocalPlugin",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
                ("enabled", models.BooleanField(default=False)),
                ("last_error", models.TextField(blank=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Local Plugin",
                "ordering": ("name",),
            },
        ),
    ]
