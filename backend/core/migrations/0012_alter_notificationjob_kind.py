from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_alter_notificationjob_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificationjob",
            name="kind",
            field=models.CharField(
                choices=[
                    ("quote_customer_email", "Quote customer email"),
                    ("quote_staff_email", "Quote staff email"),
                    ("quote_webhook", "Quote Power Automate webhook"),
                    ("quote_ready_email", "Quote ready email"),
                    ("quote_message_email", "Quote message email"),
                    ("order_status_email", "Order status email"),
                    ("order_status_webhook", "Order status webhook"),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
    ]
