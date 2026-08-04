import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_remove_legacy_content_and_portable_urls"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("quote_customer_email", "Quote customer email"),
                            ("quote_staff_email", "Quote staff email"),
                            ("quote_webhook", "Quote Power Automate webhook"),
                            ("order_status_email", "Order status email"),
                            ("order_status_webhook", "Order status webhook"),
                        ],
                        db_index=True,
                        max_length=40,
                    ),
                ),
                ("payload", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("sent", "Sent"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("available_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
            ],
            options={
                "ordering": ("available_at", "id"),
                "indexes": [models.Index(fields=["status", "available_at"], name="core_notifi_status_2f9d7b_idx")],
            },
        ),
    ]
