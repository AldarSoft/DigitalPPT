from django.db import migrations, models
from django.db.models import Count, Q


def reconcile_duplicate_successes(apps, schema_editor):
    PaymentAttempt = apps.get_model("payments", "PaymentAttempt")
    duplicate_order_ids = (
        PaymentAttempt.objects.filter(status="succeeded")
        .values("order_id")
        .annotate(success_count=Count("id"))
        .filter(success_count__gt=1)
        .values_list("order_id", flat=True)
    )
    for order_id in duplicate_order_ids:
        successful_ids = list(
            PaymentAttempt.objects.filter(order_id=order_id, status="succeeded")
            .order_by("created_at", "id")
            .values_list("id", flat=True)
        )
        PaymentAttempt.objects.filter(id__in=successful_ids[1:]).update(
            status="cancelled",
            failure_message=(
                "Duplicate successful payment reconciled during the single-payment migration."
            ),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0002_paymentattempt_expires_at_paymentattempt_paid_at_and_more"),
    ]

    operations = [
        migrations.RunPython(reconcile_duplicate_successes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.UniqueConstraint(
                fields=("order",),
                condition=Q(status="succeeded"),
                name="payments_one_success_per_order",
            ),
        ),
    ]
