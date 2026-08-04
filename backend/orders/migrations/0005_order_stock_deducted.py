from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_remove_order_extra_costs"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="stock_deducted",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
