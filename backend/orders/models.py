from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from common.models import TimeStampedModel


class Order(TimeStampedModel):
    class Source(models.TextChoices):
        DIRECT = "direct", "Direct checkout"
        QUOTE = "quote", "Accepted quote"
        ADMIN = "admin", "Admin created"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        BACKORDERED = "backordered", "Awaiting stock"
        SCHEDULED = "scheduled", "Scheduled"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_created_orders",
    )
    organization = models.ForeignKey(
        "licensing.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    renewal_license = models.ForeignKey(
        "licensing.License",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="renewal_orders",
    )
    quote_request = models.ForeignKey(
        "quotes.QuoteRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.ADMIN,
        db_index=True,
    )
    checkout_key = models.UUIDField(null=True, blank=True, unique=True)
    order_number = models.CharField(max_length=40, unique=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    customer_first_name = models.CharField(max_length=150)
    customer_last_name = models.CharField(max_length=150)
    customer_email = models.EmailField(db_index=True)
    customer_phone = models.CharField(max_length=32, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    shipping_address = models.CharField(max_length=255)
    shipping_city = models.CharField(max_length=120)
    shipping_state = models.CharField(max_length=120, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)
    shipping_country = models.CharField(max_length=120)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_deducted = models.BooleanField(default=False, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["source", "status"]),
            models.Index(fields=["quote_request", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["customer_email", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.order_number:
            self.order_number = f"ORD-{self.created_at.year}-{self.pk:06d}"
            super().save(update_fields=["order_number"])
        self._sync_quote_status()

    def _sync_quote_status(self):
        if not self.quote_request_id:
            return

        from quotes.models import QuoteRequest

        if self.status == self.Status.CANCELLED:
            target_status = QuoteRequest.Status.CANCELLED
        elif self.payment_attempts.filter(status="succeeded").exists():
            target_status = QuoteRequest.Status.PAYMENT_CONFIRMED
        elif self.status == self.Status.PENDING:
            invoice_states = {
                QuoteRequest.Status.INVOICE_SENT,
                QuoteRequest.Status.AWAITING_PAYMENT,
                QuoteRequest.Status.PAYMENT_REJECTED,
            }
            target_status = (
                self.quote_request.status
                if self.quote_request.status in invoice_states
                else QuoteRequest.Status.AWAITING_PAYMENT
            )
        else:
            target_status = self.quote_request.status

        clear_rejection = bool(
            target_status == QuoteRequest.Status.PAYMENT_CONFIRMED
            and self.quote_request.payment_rejection_reason
        )
        if self.quote_request.status != target_status or clear_rejection:
            previous_status = self.quote_request.status
            self.quote_request.status = target_status
            update_fields = ["status", "updated_at"]
            if clear_rejection:
                self.quote_request.payment_rejection_reason = ""
                update_fields.append("payment_rejection_reason")
            self.quote_request.save(update_fields=update_fields)
            from core.notifications import publish_quote_status_changed

            transaction.on_commit(
                lambda quote_id=self.quote_request_id, old=previous_status, new=target_status:
                publish_quote_status_changed(quote_id, old, new)
            )

    def __str__(self):
        return self.order_number or f"Order {self.pk}"


class OrderItem(TimeStampedModel):
    class FulfillmentStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        READY = "ready", "Ready to ship"
        PARTIALLY_READY = "partially_ready", "Partially ready"
        BACKORDERED = "backordered", "Awaiting stock"
        FULFILLED = "fulfilled", "Fulfilled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    reserved_quantity = models.PositiveIntegerField(default=0)
    backordered_quantity = models.PositiveIntegerField(default=0)
    fulfillment_status = models.CharField(
        max_length=24,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.NOT_REQUIRED,
        db_index=True,
    )
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ("id",)
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
        indexes = [
            models.Index(fields=["order", "product"]),
            models.Index(fields=["fulfillment_status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reserved_quantity__lte=models.F("quantity")),
                name="orders_item_reserved_quantity_not_over_ordered",
            ),
            models.CheckConstraint(
                condition=models.Q(backordered_quantity__lte=models.F("quantity")),
                name="orders_item_backordered_quantity_not_over_ordered",
            ),
        ]

    def __str__(self):
        return f"{self.order} - {self.product_name}"


class InventoryReservation(TimeStampedModel):
    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        CONSUMED = "consumed", "Consumed"
        RELEASED = "released", "Released"

    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="inventory_reservation",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="inventory_reservations",
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RESERVED,
        db_index=True,
    )
    consumed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["product", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name="orders_inventory_reservation_positive_quantity",
            ),
        ]

    def __str__(self):
        return f"{self.product} x {self.quantity} for {self.order_item.order}"


class Shipment(TimeStampedModel):
    """A dispatched delivery of reserved units for one order.

    Created only when stock is actually shipped: on-hand and reserved
    quantities are reduced together and the shipment rows form the
    fulfillment audit trail.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="shipments",
    )
    idempotency_key = models.UUIDField(unique=True, editable=False)
    shipment_number = models.CharField(max_length=40, unique=True, blank=True)
    carrier = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    shipped_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_shipments",
    )
    shipping_address = models.CharField(max_length=255)
    shipping_city = models.CharField(max_length=120)
    shipping_state = models.CharField(max_length=120, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)
    shipping_country = models.CharField(max_length=120)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["order", "shipped_at"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.shipment_number:
            self.shipment_number = f"SHP-{self.created_at.year}-{self.pk:06d}"
            super().save(update_fields=["shipment_number"])

    def __str__(self):
        return self.shipment_number or f"Shipment {self.pk}"


class ShipmentItem(TimeStampedModel):
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="items",
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="shipment_items",
    )
    quantity = models.PositiveIntegerField()
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ("id",)
        indexes = [
            models.Index(fields=["shipment", "order_item"]),
            models.Index(fields=["order_item", "shipment"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="orders_shipment_item_positive_quantity",
            ),
            models.UniqueConstraint(
                fields=["shipment", "order_item"],
                name="orders_shipment_item_unique_shipment_order_item",
            ),
        ]

    def __str__(self):
        return f"{self.shipment} - {self.product_name} x {self.quantity}"
