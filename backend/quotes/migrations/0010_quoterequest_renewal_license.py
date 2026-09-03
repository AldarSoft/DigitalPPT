from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("licensing", "0006_alter_licenseevent_event_type"),
        ("quotes", "0009_quoterequest_payment_rejection_reason_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="quoterequest",
            name="renewal_license",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="renewal_quote_requests",
                to="licensing.license",
            ),
        ),
    ]
