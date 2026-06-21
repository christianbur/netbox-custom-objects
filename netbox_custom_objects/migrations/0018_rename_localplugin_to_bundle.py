from django.db import migrations, models


class Migration(migrations.Migration):
    """Rename the CO drop-in ``LocalPlugin`` model to ``Bundle``.

    This is the CO-owned "bundle" concept (packages under the local path), not
    NetBox's own plugin system. ``RenameModel`` renames the backing table in
    place, so existing rows and their ``enabled`` state are preserved.

    The ``id`` ``AlterField`` resolves a pre-existing drift (the model resolves
    to NetBox's default ``BigAutoField`` while migration ``0016`` recorded a
    plain ``AutoField``); folding it in here keeps ``makemigrations --check``
    clean.  On PostgreSQL the column is already ``bigint`` for fresh installs,
    so this is effectively a no-op state correction.
    """

    dependencies = [
        ("netbox_custom_objects", "0017_customobjecttypefield_object_proxy"),
    ]

    operations = [
        migrations.RenameModel(old_name="LocalPlugin", new_name="Bundle"),
        migrations.AlterModelOptions(
            name="bundle",
            options={"ordering": ("name",), "verbose_name": "Bundle"},
        ),
        migrations.AlterField(
            model_name="bundle",
            name="id",
            field=models.BigAutoField(
                auto_created=True,
                primary_key=True,
                serialize=False,
                verbose_name="ID",
            ),
        ),
    ]
