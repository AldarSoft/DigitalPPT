from __future__ import annotations

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel
from common.storage import private_media_storage


class QuoteRequest(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWING = "reviewing", "Reviewing"
        QUOTE_APPROVED = "quote_approved", "Quote approved"
        INVOICE_SENT = "invoice_sent", "Invoice sent"
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        PAYMENT_CONFIRMED = "payment_confirmed", "Payment confirmed"
        PAYMENT_REJECTED = "payment_rejected", "Payment rejected"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quote_requests",
    )
    renewal_license = models.ForeignKey(
        "licensing.License",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="renewal_quote_requests",
    )
    quote_number = models.CharField(max_length=40, unique=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    requester_company_name = models.CharField(max_length=255, blank=True)
    requester_contact_person = models.CharField(max_length=255)
    requester_email = models.EmailField(db_index=True)
    requester_phone = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)
    admin_message = models.TextField(blank=True)
    quoted_subtotal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quoted_shipping = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quoted_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quoted_at = models.DateTimeField(null=True, blank=True)
    admin_agreed = models.BooleanField(default=False)
    customer_agreed = models.BooleanField(default=False)
    invoice_number = models.CharField(max_length=40, unique=True, blank=True, null=True)
    payment_rejection_reason = models.TextField(blank=True)
    invoice_pdf = models.FileField(
        upload_to="quotes/invoices/",
        storage=private_media_storage,
        blank=True,
    )
    invoiced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Quote Request"
        verbose_name_plural = "Quote Requests"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["requester_email", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.quote_number:
            self.quote_number = f"QTE-{self.created_at.year}-{self.pk:06d}"
            super().save(update_fields=["quote_number"])

    def __str__(self):
        return self.quote_number or f"Quote {self.pk}"


class QuoteRequestItem(TimeStampedModel):
    quote_request = models.ForeignKey(
        QuoteRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "products.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    specifications = models.JSONField(default=dict, blank=True)
    quoted_unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quoted_line_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ("id",)
        verbose_name = "Quote Request Item"
        verbose_name_plural = "Quote Request Items"
        indexes = [
            models.Index(fields=["quote_request", "product"]),
        ]

    def __str__(self):
        return f"{self.quote_request} - {self.product_name}"


class QuoteMessage(TimeStampedModel):
    class SenderRole(models.TextChoices):
        ADMIN = "admin", "Admin"
        CUSTOMER = "customer", "Customer"

    quote_request = models.ForeignKey(
        QuoteRequest,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quote_messages",
    )
    sender_role = models.CharField(max_length=20, choices=SenderRole.choices)
    body = models.TextField()

    class Meta:
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=["quote_request", "created_at"])]

    def __str__(self):
        return f"{self.quote_request} - {self.sender_role}"
