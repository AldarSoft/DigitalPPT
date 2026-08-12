import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def seed_providers(apps, schema_editor):
    PaymentProvider = apps.get_model("payments", "PaymentProvider")
    providers = [
        ("stripe", "Stripe", 0),
        ("paypal", "PayPal", 1),
        ("qpay", "QPay", 2),
        ("bank_transfer", "Bank transfer", 3),
    ]
    for code, display_name, sort_order in providers:
        PaymentProvider.objects.update_or_create(
            code=code,
            defaults={"display_name": display_name, "sort_order": sort_order, "is_enabled": True, "test_mode": True},
        )


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0005_order_stock_deducted"),
    ]
    operations = [
        migrations.CreateModel(
            name="PaymentProvider",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(choices=[("stripe", "Stripe"), ("paypal", "PayPal"), ("qpay", "QPay"), ("bank_transfer", "Bank transfer")], max_length=40, unique=True)),
                ("display_name", models.CharField(max_length=120)),
                ("is_enabled", models.BooleanField(db_index=True, default=True)),
                ("test_mode", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={"verbose_name": "Payment Provider", "verbose_name_plural": "Payment Providers", "ordering": ("sort_order", "id")},
        ),
        migrations.CreateModel(
            name="PaymentAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reference", models.CharField(blank=True, max_length=48, unique=True)),
                ("idempotency_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="USD", max_length=10)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("succeeded", "Succeeded"), ("failed", "Failed")], db_index=True, default="pending", max_length=20)),
                ("is_test", models.BooleanField(db_index=True, default=True)),
                ("external_reference", models.CharField(blank=True, max_length=255)),
                ("failure_message", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_payment_attempts", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_attempts", to="orders.order")),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attempts", to="payments.paymentprovider")),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(model_name="paymentattempt", index=models.Index(fields=["order", "status"], name="payments_pa_order_i_d0489d_idx")),
        migrations.AddIndex(model_name="paymentattempt", index=models.Index(fields=["provider", "created_at"], name="payments_pa_provide_1c1d46_idx")),
        migrations.RunPython(seed_providers, migrations.RunPython.noop),
    ]
