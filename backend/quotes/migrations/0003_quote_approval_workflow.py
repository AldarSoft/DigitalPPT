from django.db import migrations, models


def separate_pending_quote_orders(apps, schema_editor):
    QuoteRequest = apps.get_model("quotes", "QuoteRequest")
    Order = apps.get_model("orders", "Order")

    pending_orders = Order.objects.filter(
        quote_request_id__isnull=False,
        status="pending",
    )
    pending_quote_ids = list(pending_orders.values_list("quote_request_id", flat=True))
    pending_orders.delete()
    QuoteRequest.objects.filter(id__in=pending_quote_ids).update(status="new")

    processing_quote_ids = Order.objects.filter(
        quote_request_id__isnull=False,
        status="processing",
    ).values_list("quote_request_id", flat=True)
    QuoteRequest.objects.filter(id__in=processing_quote_ids).update(status="approved")


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_order_stock_deducted"),
        ("quotes", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quoterequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("reviewing", "Reviewing"),
                    ("quoted", "Quoted"),
                    ("approved", "Approved to order"),
                    ("closed", "Closed"),
                ],
                db_index=True,
                default="new",
                max_length=20,
            ),
        ),
        migrations.RunPython(separate_pending_quote_orders, migrations.RunPython.noop),
    ]
