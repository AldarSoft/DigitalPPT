import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("licensing", "0004_alter_licenseevent_event_type"),
        ("payments", "0004_close_terminal_order_payment_attempts"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentattempt",
            name="order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payment_attempts",
                to="orders.order",
            ),
        ),
        migrations.AddField(
            model_name="paymentattempt",
            name="renewal_license",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="renewal_payment_attempts",
                to="licensing.license",
            ),
        ),
        migrations.AddIndex(
            model_name="paymentattempt",
            index=models.Index(fields=["renewal_license", "status"], name="payments_pa_renewal_c9299b_idx"),
        ),
    ]
