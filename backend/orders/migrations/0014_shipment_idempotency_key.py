from uuid import uuid4

from django.db import migrations, models


def populate_shipment_keys(apps, schema_editor):
    Shipment = apps.get_model("orders", "Shipment")
    for shipment in Shipment.objects.filter(idempotency_key__isnull=True).iterator():
        shipment.idempotency_key = uuid4()
        shipment.save(update_fields=["idempotency_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0013_shipment_shipmentitem_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="shipment",
            name="idempotency_key",
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(populate_shipment_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="shipment",
            name="idempotency_key",
            field=models.UUIDField(unique=True, editable=False),
        ),
    ]
