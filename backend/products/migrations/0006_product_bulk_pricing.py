from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0005_remove_legacy_rack_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="bulk_minimum_quantity",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="bulk_unit_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
