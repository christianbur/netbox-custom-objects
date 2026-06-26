from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('netbox_custom_objects', '0014_fix_mixed_case_field_names'),
    ]

    operations = [
        migrations.AddField(
            model_name='customobjecttype',
            name='metadata',
            field=models.JSONField(
                blank=True,
                help_text='Optional structured metadata as JSON or YAML.',
                null=True,
                verbose_name='Metadata',
            ),
        ),
    ]
