from django.db import migrations, models


def distinguish_cancelled_quotes(apps, schema_editor):
    QuoteRequest = apps.get_model("quotes", "QuoteRequest")
    Order = apps.get_model("orders", "Order")

    active_quote_ids = Order.objects.filter(
        status__in=("scheduled", "processing", "completed"),
        quote_request_id__isnull=False,
    ).values_list("quote_request_id", flat=True)
    QuoteRequest.objects.filter(status="closed", id__in=active_quote_ids).update(
        status="approved"
    )
    QuoteRequest.objects.filter(status="closed").update(status="cancelled")


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_alter_order_status"),
        ("quotes", "0006_quoterequest_admin_agreed_and_more"),
    ]

    operations = [
        migrations.RunPython(distinguish_cancelled_quotes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="quoterequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("reviewing", "Reviewing"),
                    ("quoted", "Invoice sent"),
                    ("approved", "Converted"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="new",
                max_length=20,
            ),
        ),
    ]
