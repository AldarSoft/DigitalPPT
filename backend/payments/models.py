from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class PaymentProvider(TimeStampedModel):
    class Code(models.TextChoices):
        STRIPE = "stripe", "Stripe"
        PAYPAL = "paypal", "PayPal"
        QPAY = "qpay", "QPay"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"

    code = models.CharField(max_length=40, choices=Code.choices, unique=True)
    display_name = models.CharField(max_length=120)
    is_enabled = models.BooleanField(default=True, db_index=True)
    test_mode = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Payment Provider"
        verbose_name_plural = "Payment Providers"

    def __str__(self):
        return self.display_name


class PaymentAttempt(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        REFUNDED = "refunded", "Refunded"

    reference = models.CharField(max_length=48, unique=True, blank=True)
    idempotency_key = models.UUIDField(default=uuid4, unique=True, editable=False)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    provider = models.ForeignKey(
        PaymentProvider,
        on_delete=models.PROTECT,
        related_name="attempts",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    is_test = models.BooleanField(default=True, db_index=True)
    external_reference = models.CharField(max_length=255, blank=True)
    failure_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_payment_attempts",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["order", "status"]),
            models.Index(fields=["provider", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(status="succeeded"),
                name="payments_one_success_per_order",
            ),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f"PAY-{self.created_at.year}-{self.pk:06d}"
            super().save(update_fields=["reference"])

    def __str__(self):
        return self.reference or f"Payment attempt {self.pk}"
