from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_remove_legacy_rack_banner"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesetting",
            name="commerce_defaults_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
