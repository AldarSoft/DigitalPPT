from django.db import migrations


def close_terminal_order_payment_attempts(apps, schema_editor):
    PaymentAttempt = apps.get_model("payments", "PaymentAttempt")
    PaymentAttempt.objects.filter(
        status="pending",
        order__status__in=("completed", "cancelled"),
    ).update(
        status="cancelled",
        failure_message="Closed because the related order is already terminal.",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_alter_order_status"),
        ("payments", "0003_one_successful_payment_per_order"),
    ]

    operations = [
        migrations.RunPython(
            close_terminal_order_payment_attempts,
            migrations.RunPython.noop,
        ),
    ]
