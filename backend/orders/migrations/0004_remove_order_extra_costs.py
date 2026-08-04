from django.db import migrations
from django.db.models import F


def remove_order_extra_costs(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.update(
        tax_amount=0,
        shipping_fee=0,
        total=F("subtotal"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0003_order_quote_request_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_order_extra_costs, migrations.RunPython.noop),
    ]
