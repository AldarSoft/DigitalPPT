from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
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
    is_customer_available = models.BooleanField(default=False, db_index=True)
    test_mode = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Payment Provider"
        verbose_name_plural = "Payment Providers"

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        if (
            self.code != self.Code.BANK_TRANSFER
            and self.test_mode
            and self.is_customer_available
            and not (settings.DEBUG and settings.PAYMENTS_DEVELOPMENT_SIMULATOR)
        ):
            raise ValidationError(
                "Test payment providers cannot be offered to production customers."
            )
        return super().save(*args, **kwargs)


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
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    renewal_license = models.ForeignKey(
        "licensing.License",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="renewal_payment_attempts",
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
            models.Index(fields=["renewal_license", "status"]),
            models.Index(fields=["provider", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(status="succeeded"),
                name="payments_one_success_per_order",
            ),
            models.UniqueConstraint(
                fields=["provider", "external_reference"],
                condition=(
                    models.Q(status="succeeded")
                    & ~models.Q(external_reference="")
                ),
                name="payments_unique_confirmed_external_reference",
            ),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f"PAY-{self.created_at.year}-{self.pk:06d}"
            super().save(update_fields=["reference"])

    def __str__(self):
        return self.reference or f"Payment attempt {self.pk}"


class PaymentProviderEvent(TimeStampedModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    provider = models.ForeignKey(
        PaymentProvider,
        on_delete=models.PROTECT,
        related_name="events",
    )
    event_id = models.CharField(max_length=255)
    payment_attempt = models.ForeignKey(
        PaymentAttempt,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="provider_events",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED,
        db_index=True,
    )
    payload_sha256 = models.CharField(max_length=64)
    provider_transaction_id = models.CharField(max_length=255, blank=True)
    outcome = models.CharField(max_length=32, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                name="payments_provider_event_unique_provider_event",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.provider.code}: {self.event_id}"


class ImmutablePaymentStatusEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Payment status events are immutable.")

    def delete(self):
        raise ValidationError("Payment status events are immutable.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Payment status events are immutable.")


class PaymentStatusEvent(models.Model):
    class EventType(models.TextChoices):
        ATTEMPT_CREATED = "attempt_created", "Attempt created"
        MANUAL_CONFIRMATION = "manual_confirmation", "Manual confirmation"
        MANUAL_REJECTION = "manual_rejection", "Manual rejection"
        REFUND = "refund", "Refund"
        STATUS_CHANGE = "status_change", "Status change"

    payment_attempt = models.ForeignKey(
        PaymentAttempt,
        on_delete=models.PROTECT,
        related_name="status_events",
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    previous_status = models.CharField(max_length=20, choices=PaymentAttempt.Status.choices)
    new_status = models.CharField(max_length=20, choices=PaymentAttempt.Status.choices)
    invoice_reference = models.CharField(max_length=40, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10)
    external_reference = models.CharField(max_length=255, blank=True)
    reason = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_status_events",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    objects = ImmutablePaymentStatusEventQuerySet.as_manager()

    class Meta:
        ordering = ("created_at", "id")
        default_permissions = ("add", "view")
        indexes = [
            models.Index(fields=["payment_attempt", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Payment status events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Payment status events are immutable.")

    def __str__(self):
        return f"{self.payment_attempt.reference}: {self.event_type}"
