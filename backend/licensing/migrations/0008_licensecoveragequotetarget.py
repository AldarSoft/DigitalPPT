import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("licensing", "0007_license_billing_model"),
        ("orders", "0014_shipment_idempotency_key"),
        ("quotes", "0010_quoterequest_renewal_license"),
    ]

    operations = [
        migrations.CreateModel(
            name="LicenseCoverageQuoteTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.PositiveIntegerField()),
                ("order_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="coverage_quote_targets", to="orders.orderitem")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="coverage_quote_targets", to="licensing.organization")),
                ("quote_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="coverage_targets", to="quotes.quoterequestitem")),
                ("quote_request", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="coverage_targets", to="quotes.quoterequest")),
            ],
            options={
                "ordering": ("created_at", "id"),
                "indexes": [
                    models.Index(fields=["organization", "created_at"], name="licensing_l_organiz_025fae_idx"),
                    models.Index(fields=["order_item", "created_at"], name="licensing_l_order_i_07732d_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("quote_request", "order_item"), name="licensing_unique_coverage_quote_order_item"),
                    models.CheckConstraint(condition=models.Q(("quantity__gt", 0)), name="licensing_coverage_quote_quantity_positive"),
                ],
            },
        ),
    ]
