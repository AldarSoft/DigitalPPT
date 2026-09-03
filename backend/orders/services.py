from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from orders.models import InventoryReservation, Order, OrderItem, Shipment, ShipmentItem
from products.models import Product

logger = logging.getLogger(__name__)


class InventoryReservationService:
    @staticmethod
    def reserved_quantities(*, product_ids):
        rows = (
            InventoryReservation.objects.filter(
                product_id__in=product_ids,
                status=InventoryReservation.Status.RESERVED,
            )
            .values("product_id")
            .annotate(quantity=Sum("quantity"))
        )
        return {row["product_id"]: row["quantity"] for row in rows}

    @staticmethod
    def item_quantities(*, order):
        quantities = {}
        for item in order.items.all():
            if item.product_id and item.product.is_stock_tracked:
                quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
        return quantities

    @staticmethod
    def available_quantity(*, product, reserved_quantity=0):
        return max(0, product.inventory_quantity - reserved_quantity)

    @staticmethod
    def reserve_for_order(*, order):
        if order.stock_deducted:
            return []

        items = list(
            OrderItem.objects.select_for_update()
            .select_related("product")
            .filter(order=order)
        )
        physical_items = [item for item in items if item.product_id and item.product.is_stock_tracked]
        if not physical_items:
            return []

        product_ids = {item.product_id for item in physical_items}
        products = Product.objects.select_for_update().in_bulk(product_ids)
        existing = {
            reservation.order_item_id: reservation
            for reservation in InventoryReservation.objects.select_for_update().filter(
                order_item_id__in=[item.pk for item in physical_items]
            )
        }
        reserved = InventoryReservationService.reserved_quantities(product_ids=product_ids)
        reservations = []
        for item in physical_items:
            product = products.get(item.product_id)
            reservation = existing.get(item.pk)
            current_reserved = (
                reservation.quantity
                if reservation and reservation.status == InventoryReservation.Status.RESERVED
                else 0
            )
            available = InventoryReservationService.available_quantity(
                product=product,
                reserved_quantity=reserved.get(item.product_id, 0),
            ) if product else 0
            quantity_to_reserve = min(item.quantity - current_reserved, available)
            total_reserved = current_reserved + quantity_to_reserve

            if reservation and reservation.status == InventoryReservation.Status.RESERVED:
                if quantity_to_reserve:
                    reservation.quantity = total_reserved
                    reservation.save(update_fields=["quantity", "updated_at"])
                    reserved[item.product_id] = reserved.get(item.product_id, 0) + quantity_to_reserve
                reservations.append(reservation)
            elif total_reserved:
                if reservation:
                    reservation.product = product
                    reservation.quantity = total_reserved
                    reservation.status = InventoryReservation.Status.RESERVED
                    reservation.consumed_at = None
                    reservation.released_at = None
                    reservation.release_reason = ""
                    reservation.save()
                else:
                    reservation = InventoryReservation.objects.create(
                        order_item=item,
                        product=product,
                        quantity=total_reserved,
                    )
                reserved[item.product_id] = reserved.get(item.product_id, 0) + quantity_to_reserve
                reservations.append(reservation)

            item.reserved_quantity = total_reserved
            item.backordered_quantity = item.quantity - total_reserved
            item.fulfillment_status = (
                OrderItem.FulfillmentStatus.READY
                if not item.backordered_quantity
                else OrderItem.FulfillmentStatus.PARTIALLY_READY
                if total_reserved
                else OrderItem.FulfillmentStatus.BACKORDERED
            )
            item.save(update_fields=[
                "reserved_quantity",
                "backordered_quantity",
                "fulfillment_status",
                "updated_at",
            ])
        return reservations

    @staticmethod
    @transaction.atomic
    def reserve_backorders_for_product(*, product_id):
        """Allocate newly available stock to paid backorders in order sequence."""
        product = Product.objects.select_for_update().filter(pk=product_id).first()
        if not product or not product.is_stock_tracked:
            return []

        reserved = InventoryReservationService.reserved_quantities(product_ids=[product.pk])
        available = InventoryReservationService.available_quantity(
            product=product,
            reserved_quantity=reserved.get(product.pk, 0),
        )
        if not available:
            return []

        items = list(
            OrderItem.objects.select_for_update()
            .select_related("order")
            .filter(
                product=product,
                backordered_quantity__gt=0,
                order__status__in=(
                    Order.Status.BACKORDERED,
                    Order.Status.SCHEDULED,
                    Order.Status.PROCESSING,
                ),
            )
            .order_by("order__created_at", "id")
        )
        changed_orders = set()
        for item in items:
            if not available:
                break
            allocation = min(item.backordered_quantity, available)
            reservation = InventoryReservation.objects.select_for_update().filter(order_item=item).first()
            if reservation:
                if reservation.status == InventoryReservation.Status.RESERVED:
                    reservation.quantity += allocation
                else:
                    # A consumed or released reservation no longer holds stock;
                    # the new allocation is the whole reserved amount again.
                    reservation.quantity = allocation
                reservation.status = InventoryReservation.Status.RESERVED
                reservation.consumed_at = None
                reservation.released_at = None
                reservation.release_reason = ""
                reservation.save(update_fields=[
                    "quantity", "status", "consumed_at", "released_at", "release_reason", "updated_at",
                ])
            else:
                InventoryReservation.objects.create(order_item=item, product=product, quantity=allocation)
            item.reserved_quantity += allocation
            item.backordered_quantity -= allocation
            item.fulfillment_status = (
                OrderItem.FulfillmentStatus.READY
                if not item.backordered_quantity
                else OrderItem.FulfillmentStatus.PARTIALLY_READY
            )
            item.save(update_fields=[
                "reserved_quantity", "backordered_quantity", "fulfillment_status", "updated_at",
            ])
            available -= allocation
            changed_orders.add(item.order_id)

        for order_id in changed_orders:
            order = Order.objects.prefetch_related("items__product").get(pk=order_id)
            if order.status == Order.Status.BACKORDERED and not order.items.filter(
                backordered_quantity__gt=0
            ).exists():
                OrderService.update_status(order=order, new_status=Order.Status.SCHEDULED)
        return list(changed_orders)

    @staticmethod
    def consume_for_order(*, order):
        reservations = list(
            InventoryReservation.objects.select_for_update()
            .select_related("product")
            .filter(
                order_item__order=order,
                status=InventoryReservation.Status.RESERVED,
            )
        )
        if not reservations:
            return False

        quantities = {}
        for reservation in reservations:
            quantities[reservation.product_id] = quantities.get(reservation.product_id, 0) + reservation.quantity
        products = Product.objects.select_for_update().in_bulk(quantities)
        stock_errors = {}
        for product_id, quantity in quantities.items():
            product = products.get(product_id)
            available = product.inventory_quantity if product else 0
            if available < quantity:
                stock_errors[str(product_id)] = f"Only {available} units remain on hand; {quantity} required."
        if stock_errors:
            raise ValidationError({"inventory": stock_errors})

        for product_id, quantity in quantities.items():
            product = products[product_id]
            product.inventory_quantity -= quantity
            product.save(update_fields=["inventory_quantity", "updated_at"])
        now = timezone.now()
        InventoryReservation.objects.filter(pk__in=[reservation.pk for reservation in reservations]).update(
            quantity=0,
            status=InventoryReservation.Status.CONSUMED,
            consumed_at=now,
            updated_at=now,
        )
        items = {
            item.pk: item
            for item in OrderItem.objects.filter(
                pk__in=[reservation.order_item_id for reservation in reservations]
            )
        }
        for reservation in reservations:
            item = items.get(reservation.order_item_id)
            if not item:
                continue
            # A partially reserved line still awaits stock for its remainder.
            item.fulfillment_status = (
                OrderItem.FulfillmentStatus.FULFILLED
                if not item.backordered_quantity
                else OrderItem.FulfillmentStatus.BACKORDERED
            )
            item.reserved_quantity = 0
            item.save(update_fields=["reserved_quantity", "fulfillment_status", "updated_at"])
        return True

    @staticmethod
    def release_for_order(*, order, reason):
        released = InventoryReservation.objects.filter(
            order_item__order=order,
            status=InventoryReservation.Status.RESERVED,
        ).update(
            status=InventoryReservation.Status.RELEASED,
            released_at=timezone.now(),
            release_reason=reason[:255],
            updated_at=timezone.now(),
        )
        OrderItem.objects.filter(order=order).exclude(
            reserved_quantity=0,
            backordered_quantity=0,
        ).update(
            reserved_quantity=0,
            backordered_quantity=0,
            fulfillment_status=OrderItem.FulfillmentStatus.NOT_REQUIRED,
            updated_at=timezone.now(),
        )
        return released


def _item_fulfillment_status(item: OrderItem) -> str:
    """Derive the fulfillment state from the reserved and backordered counts."""
    if item.reserved_quantity and item.backordered_quantity:
        return OrderItem.FulfillmentStatus.PARTIALLY_READY
    if item.reserved_quantity:
        return OrderItem.FulfillmentStatus.READY
    if item.backordered_quantity:
        return OrderItem.FulfillmentStatus.BACKORDERED
    return OrderItem.FulfillmentStatus.FULFILLED


class ShipmentService:
    """Dispatch reserved units and record the shipment as fulfillment history."""

    @staticmethod
    @transaction.atomic
    def create_shipment(
        *,
        order_number: str,
        items,
        idempotency_key=None,
        carrier: str = "",
        tracking_number: str = "",
        notes: str = "",
        actor=None,
    ):
        from payments.models import PaymentAttempt

        existing_shipment = (
            Shipment.objects.select_for_update()
            .select_related("order")
            .filter(idempotency_key=idempotency_key)
            .first()
        ) if idempotency_key else None
        if existing_shipment:
            if existing_shipment.order.order_number != order_number:
                raise ValidationError({"idempotency_key": "This key is already in use."})
            return (
                Order.objects.select_related("user", "organization")
                .prefetch_related("items__product", "shipments__items")
                .get(pk=existing_shipment.order_id)
            )

        order = Order.objects.select_for_update().filter(order_number=order_number).first()
        if not order:
            raise ValidationError({"order_number": "Order not found."})
        if not PaymentAttempt.objects.filter(
            order=order,
            status=PaymentAttempt.Status.SUCCEEDED,
        ).exists():
            raise ValidationError({"status": "Only paid orders can be shipped."})
        if order.status not in {
            Order.Status.BACKORDERED,
            Order.Status.SCHEDULED,
            Order.Status.PROCESSING,
        }:
            raise ValidationError({"status": f"Orders in “{order.status}” state cannot be shipped."})
        if not items:
            raise ValidationError({"items": "Add at least one item to ship."})

        requested = {}
        for entry in items:
            item_id = entry.get("order_item_id") or entry.get("id")
            quantity = entry.get("quantity")
            if not isinstance(item_id, int) or item_id <= 0:
                raise ValidationError({"items": "Each shipment line requires a valid order item."})
            if not isinstance(quantity, int) or quantity <= 0:
                raise ValidationError({"items": f"Ship at least one unit for item {item_id}."})
            if item_id in requested:
                raise ValidationError({"items": f"Item {item_id} is listed more than once."})
            requested[item_id] = quantity

        order_items = list(
            OrderItem.objects.select_for_update()
            .select_related("product")
            .filter(order=order)
        )
        item_map = {item.pk: item for item in order_items}
        reservations = {
            reservation.order_item_id: reservation
            for reservation in InventoryReservation.objects.select_for_update().filter(
                order_item__order=order,
                status=InventoryReservation.Status.RESERVED,
            )
        }

        shipment_lines = []
        errors = {}
        for item_id, quantity in requested.items():
            item = item_map.get(item_id)
            if not item:
                errors[str(item_id)] = "This item does not belong to the order."
                continue
            if not item.product_id or not item.product.is_stock_tracked:
                errors[str(item_id)] = "This product has no physical stock to ship."
                continue
            reservation = reservations.get(item_id)
            if not reservation:
                errors[str(item_id)] = "No reserved stock is available for this item."
                continue
            if quantity > reservation.quantity:
                errors[str(item_id)] = (
                    f"Only {reservation.quantity} reserved unit(s) can be shipped; "
                    f"{quantity} requested."
                )
                continue
            shipment_lines.append((item, reservation, quantity))
        if errors:
            raise ValidationError({"items": errors})

        product_totals = {}
        for item, _reservation, quantity in shipment_lines:
            product_totals[item.product_id] = product_totals.get(item.product_id, 0) + quantity
        products = Product.objects.select_for_update().in_bulk(product_totals)
        stock_errors = {}
        for product_id, quantity in product_totals.items():
            product = products.get(product_id)
            available = product.inventory_quantity if product else 0
            if available < quantity:
                stock_errors[str(product_id)] = (
                    f"Only {available} units remain on hand; {quantity} required."
                )
        if stock_errors:
            raise ValidationError({"inventory": stock_errors})

        shipment = Shipment.objects.create(
            order=order,
            idempotency_key=idempotency_key or uuid4(),
            carrier=carrier.strip(),
            tracking_number=tracking_number.strip(),
            notes=notes.strip(),
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
            shipping_address=order.shipping_address,
            shipping_city=order.shipping_city,
            shipping_state=order.shipping_state,
            shipping_postal_code=order.shipping_postal_code,
            shipping_country=order.shipping_country,
        )
        ShipmentItem.objects.bulk_create([
            ShipmentItem(
                shipment=shipment,
                order_item=item,
                quantity=quantity,
                product_name=item.product_name,
                sku=item.sku,
            )
            for item, _reservation, quantity in shipment_lines
        ])

        # Shipping reduces on-hand and reserved quantities together.
        for product_id, quantity in product_totals.items():
            product = products[product_id]
            product.inventory_quantity -= quantity
            product.save(update_fields=["inventory_quantity", "updated_at"])
        now = timezone.now()
        for item, reservation, quantity in shipment_lines:
            remaining = reservation.quantity - quantity
            if remaining:
                reservation.quantity = remaining
                reservation.save(update_fields=["quantity", "updated_at"])
            else:
                reservation.quantity = 0
                reservation.status = InventoryReservation.Status.CONSUMED
                reservation.consumed_at = now
                reservation.save(update_fields=["quantity", "status", "consumed_at", "updated_at"])
            item.reserved_quantity = remaining
            item.fulfillment_status = _item_fulfillment_status(item)
            item.save(update_fields=["reserved_quantity", "fulfillment_status", "updated_at"])

        order.stock_deducted = True
        order.save(update_fields=["stock_deducted", "updated_at"])

        physical_items = [
            item for item in order_items
            if item.product_id and item.product.is_stock_tracked
        ]
        remaining_backordered = any(item.backordered_quantity for item in physical_items)
        remaining_reserved = any(item.reserved_quantity for item in physical_items)
        if remaining_reserved or remaining_backordered:
            target_status = (
                Order.Status.BACKORDERED
                if remaining_backordered
                else Order.Status.SCHEDULED
            )
        else:
            target_status = Order.Status.COMPLETED

        if target_status != order.status and target_status in OrderService.ALLOWED_STATUS_TRANSITIONS.get(
            order.status, set()
        ):
            OrderService.update_status(order=order, new_status=target_status)

        from core.notifications import publish_order_shipped

        transaction.on_commit(
            lambda shipment_id=shipment.pk: publish_order_shipped(shipment_id)
        )

        logger.info(
            "Shipment %s created for order %s with %s line(s)",
            shipment.shipment_number,
            order.order_number,
            len(shipment_lines),
        )
        return (
            Order.objects.select_related("user", "organization")
            .prefetch_related("items__product", "shipments__items")
            .get(pk=order.pk)
        )


class OrderService:
    ALLOWED_STATUS_TRANSITIONS = {
        Order.Status.DRAFT: {
            Order.Status.PENDING,
            Order.Status.CANCELLED,
        },
        Order.Status.PENDING: {
            Order.Status.BACKORDERED,
            Order.Status.SCHEDULED,
            Order.Status.PROCESSING,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        },
        Order.Status.PROCESSING: {
            Order.Status.BACKORDERED,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        },
        Order.Status.SCHEDULED: {
            Order.Status.BACKORDERED,
            Order.Status.PROCESSING,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        },
        Order.Status.BACKORDERED: {
            Order.Status.SCHEDULED,
            Order.Status.CANCELLED,
        },
        Order.Status.COMPLETED: set(),
        Order.Status.CANCELLED: set(),
    }

    @staticmethod
    @transaction.atomic
    def create_order(*, validated_data, user=None):
        items_data = validated_data.pop("items")
        quote_request = validated_data.pop("quote_request", None)
        renewal_license = validated_data.pop("renewal_license", None)
        validated_data.pop("quote_number", None)
        tax_amount = validated_data.pop("tax_amount", Decimal("0.00"))
        shipping_fee = validated_data.pop("shipping_fee", Decimal("0.00"))
        organization = validated_data.pop("organization", None)
        authenticated_user = user if user and user.is_authenticated else None
        order_user = authenticated_user

        if authenticated_user and authenticated_user.is_staff:
            User = get_user_model()
            order_user = quote_request.user if quote_request and quote_request.user else (
                User.objects.filter(email__iexact=validated_data.get("customer_email")).first()
                or authenticated_user
            )

        if organization is None and order_user and not order_user.is_staff:
            from licensing.services import OrganizationSummaryService

            membership = OrganizationSummaryService.membership_for_user(order_user)
            organization = membership.organization if membership else None

        order = Order.objects.create(
            user=order_user,
            organization=organization,
            quote_request=quote_request,
            renewal_license=renewal_license,
            source=Order.Source.QUOTE if quote_request else Order.Source.ADMIN,
            **validated_data,
        )

        subtotal = Decimal("0.00")
        order_items = []
        for item_data in items_data:
            product = item_data.get("product")
            unit_price = item_data.get("unit_price") or (
                product.price_for_quantity(item_data["quantity"])
                if product
                else Decimal("0.00")
            )
            line_total = unit_price * item_data["quantity"]
            subtotal += line_total
            order_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    product_name=item_data.get("product_name") or product.name,
                    sku=item_data.get("sku") or (product.sku if product else ""),
                    unit_price=unit_price,
                    quantity=item_data["quantity"],
                    line_total=line_total,
                )
            )

        OrderItem.objects.bulk_create(order_items)
        order.subtotal = subtotal
        order.tax_amount = tax_amount
        order.shipping_fee = shipping_fee
        order.total = subtotal + tax_amount + shipping_fee
        order.save(update_fields=["subtotal", "tax_amount", "shipping_fee", "total", "updated_at"])

        logger.info("Created order %s with %s items", order.order_number, len(order_items))
        return (
            Order.objects.select_related("user", "organization")
            .prefetch_related("items__product")
            .get(pk=order.pk)
        )

    @staticmethod
    @transaction.atomic
    def create_checkout_order(*, validated_data, user=None):
        items_data = validated_data.pop("items")
        checkout_key = validated_data.pop("idempotency_key")
        requested_organization = validated_data.pop("organization", None)
        authenticated_user = user if user and user.is_authenticated else None
        if not authenticated_user:
            raise ValidationError({"detail": "Sign in before starting checkout."})

        existing = (
            Order.objects.select_for_update()
            .select_related("user")
            .prefetch_related("items__product")
            .filter(checkout_key=checkout_key)
            .first()
        )
        if existing:
            if existing.user_id != authenticated_user.id:
                raise ValidationError({"idempotency_key": "This checkout key is already in use."})
            return existing
        from licensing.services import CartLicenseService

        organization, normalized_items, _ = CartLicenseService.normalize_checkout_items(
            user=authenticated_user,
            items=items_data,
            organization_id=requested_organization.pk if requested_organization else None,
            lock=True,
        )
        if requested_organization and organization is None:
            raise ValidationError({"organization": "Select an organization you can manage."})
        product_ids = [product.pk for product, _ in normalized_items]
        products = Product.objects.select_for_update().public().in_bulk(product_ids)

        subtotal = Decimal("0.00")
        prepared_items = []
        reserved_quantities = InventoryReservationService.reserved_quantities(product_ids=product_ids)
        inventory_errors = {}
        for requested_product, quantity in normalized_items:
            product = products.get(requested_product.pk)
            if not product:
                raise ValidationError({"items": "A product is no longer available."})
            available = InventoryReservationService.available_quantity(
                product=product,
                reserved_quantity=reserved_quantities.get(product.pk, 0),
            )
            if product.is_stock_tracked and available < quantity:
                inventory_errors[str(product.pk)] = (
                    f"Only {available} units are available."
                )
                continue
            unit_price = product.price_for_quantity(quantity)
            line_total = unit_price * quantity
            subtotal += line_total
            prepared_items.append(
                OrderItem(
                    product=product,
                    product_name=product.name,
                    sku=product.sku,
                    unit_price=unit_price,
                    quantity=quantity,
                    line_total=line_total,
                )
            )

        if inventory_errors:
            raise ValidationError({"inventory": inventory_errors})

        order = Order.objects.create(
            user=authenticated_user,
            organization=organization,
            source=Order.Source.DIRECT,
            checkout_key=checkout_key,
            **validated_data,
        )
        for item in prepared_items:
            item.order = order
        OrderItem.objects.bulk_create(prepared_items)
        order.subtotal = subtotal
        order.total = subtotal
        order.save(update_fields=["subtotal", "total", "updated_at"])
        logger.info("Created checkout order %s", order.order_number)
        return (
            Order.objects.select_related("user", "organization")
            .prefetch_related("items__product")
            .get(pk=order.pk)
        )

    @staticmethod
    def status_after_successful_payment(*, order):
        """Return the first fulfilment status after a confirmed payment.

        License products are delivered by payment-success provisioning and do
        not require shipment or manual fulfilment. Any stock-tracked item keeps
        the order on the normal physical fulfilment route.
        """
        items = list(order.items.all())
        is_digital_only = bool(items) and all(
            item.product_id and not item.product.is_stock_tracked
            for item in items
        )
        if is_digital_only:
            return Order.Status.COMPLETED
        if any(item.backordered_quantity for item in items):
            return Order.Status.BACKORDERED
        return Order.Status.SCHEDULED

    @staticmethod
    @transaction.atomic
    def update_status(
        *,
        order,
        new_status,
        exclude_pending_payment_attempt_id=None,
        allow_paid_cancellation=False,
    ):
        locked_order = (
            Order.objects.select_for_update()
            .prefetch_related("items__product")
            .get(pk=order.pk)
        )
        if new_status == locked_order.status:
            return locked_order

        previous_status = locked_order.status

        if new_status == Order.Status.CANCELLED:
            from payments.models import PaymentAttempt

            if not allow_paid_cancellation and PaymentAttempt.objects.filter(
                order=locked_order,
                status=PaymentAttempt.Status.SUCCEEDED,
            ).exists():
                raise ValidationError({"status": "Paid orders cannot be cancelled."})

        allowed = OrderService.ALLOWED_STATUS_TRANSITIONS.get(locked_order.status, set())
        if new_status not in allowed:
            raise ValidationError(
                {"status": f"Cannot change order from {locked_order.status} to {new_status}."}
            )

        if new_status in {Order.Status.PROCESSING, Order.Status.COMPLETED} and locked_order.items.filter(
            backordered_quantity__gt=0
        ).exists():
            raise ValidationError(
                {"status": "Items on this order await stock. Ship or allocate stock for all items before completing the order."}
            )

        if new_status in {Order.Status.PROCESSING, Order.Status.COMPLETED}:
            from payments.models import PaymentAttempt

            has_paid_physical_items = (
                PaymentAttempt.objects.filter(
                    order=locked_order,
                    status=PaymentAttempt.Status.SUCCEEDED,
                ).exists()
                and locked_order.items.exclude(
                    product__licensing_role=Product.LicensingRole.LICENSE_PRODUCT
                ).filter(product__isnull=False).exists()
            )
            has_unshipped_items = locked_order.items.exclude(
                product__licensing_role=Product.LicensingRole.LICENSE_PRODUCT
            ).filter(
                product__isnull=False,
                reserved_quantity__gt=0,
            ).exists()
            if has_paid_physical_items and has_unshipped_items:
                raise ValidationError({
                    "status": "Create a shipment for reserved physical products instead of changing the order status directly."
                })

        item_quantities = InventoryReservationService.item_quantities(order=locked_order)

        should_deduct = (
            new_status in {Order.Status.PROCESSING, Order.Status.COMPLETED}
            and not locked_order.stock_deducted
        )
        should_restore = (
            new_status == Order.Status.CANCELLED and locked_order.stock_deducted
        )

        if should_deduct and item_quantities:
            reservation_consumed = InventoryReservationService.consume_for_order(order=locked_order)
            if not reservation_consumed:
                # Legacy and unpaid staff workflows have no reservation. They
                # retain the existing guarded stock-deduction behavior.
                products = Product.objects.select_for_update().in_bulk(item_quantities)
                stock_errors = {}
                for product_id, quantity in item_quantities.items():
                    product = products.get(product_id)
                    if not product or product.inventory_quantity < quantity:
                        available = product.inventory_quantity if product else 0
                        stock_errors[str(product_id)] = (
                            f"Only {available} units are available; {quantity} requested."
                        )
                if stock_errors:
                    raise ValidationError({"inventory": stock_errors})

                for product_id, quantity in item_quantities.items():
                    product = products[product_id]
                    product.inventory_quantity -= quantity
                    product.save(update_fields=["inventory_quantity", "updated_at"])
            locked_order.stock_deducted = True

        if should_restore and item_quantities:
            products = Product.objects.select_for_update().in_bulk(item_quantities)
            for product_id, quantity in item_quantities.items():
                product = products.get(product_id)
                if product:
                    product.inventory_quantity += quantity
                    product.save(update_fields=["inventory_quantity", "updated_at"])
            locked_order.stock_deducted = False

        if new_status == Order.Status.CANCELLED and not locked_order.stock_deducted:
            InventoryReservationService.release_for_order(
                order=locked_order,
                reason="Order cancelled before fulfillment.",
            )

        locked_order.status = new_status
        locked_order.save(update_fields=["status", "stock_deducted", "updated_at"])

        if new_status in {Order.Status.COMPLETED, Order.Status.CANCELLED}:
            from payments.services import PaymentService

            PaymentService.close_pending_attempts(
                order=locked_order,
                exclude_attempt_id=exclude_pending_payment_attempt_id,
                reason=f"Order changed to {new_status}.",
            )

        from core.notifications import publish_order_status_changed

        transaction.on_commit(
            lambda order_id=locked_order.pk, old=previous_status, new=new_status:
            publish_order_status_changed(order_id, old, new)
        )
        return locked_order


class AdminManualOrderService:
    @staticmethod
    @transaction.atomic
    def create(*, validated_data, actor):
        if not actor or not actor.is_staff or not (
            actor.is_superuser or actor.has_perm("users.manage_orders")
        ):
            raise ValidationError({"detail": "Order management access is required."})

        from licensing.models import Organization, OrganizationMembership
        from licensing.services import CartLicenseService, OrganizationService
        from payments.models import PaymentAttempt, PaymentProvider
        from payments.services import PaymentService
        from users.services import AccountSetupService

        customer_mode = validated_data.pop("customer_mode")
        organization_mode = validated_data.pop("organization_mode")
        payment_state = validated_data.pop("payment_state")
        payment_reference = validated_data.pop("payment_reference", "").strip()
        items = validated_data.pop("items")

        User = get_user_model()
        if customer_mode == "existing":
            customer = User.objects.filter(
                pk=validated_data.pop("customer_id", None),
                is_active=True,
                is_staff=False,
            ).first()
            if customer is None:
                raise ValidationError({"customer_id": "Select an active client account."})
            validated_data["customer_email"] = customer.email
            validated_data["customer_first_name"] = validated_data.get("customer_first_name") or customer.first_name
            validated_data["customer_last_name"] = validated_data.get("customer_last_name") or customer.last_name
            validated_data["customer_phone"] = validated_data.get("customer_phone") or customer.phone_number
        else:
            customer = AccountSetupService.create_user(
                email=validated_data["customer_email"],
                first_name=validated_data.get("customer_first_name", ""),
                last_name=validated_data.get("customer_last_name", ""),
                phone_number=validated_data.get("customer_phone", ""),
            )

        if organization_mode == "existing":
            organization = Organization.objects.filter(
                pk=validated_data.pop("organization_id", None),
                is_active=True,
                status=Organization.Status.ACTIVE,
            ).first()
            if organization is None:
                raise ValidationError({"organization_id": "Select an active organization."})
            if not OrganizationMembership.objects.filter(
                organization=organization,
                user=customer,
                is_active=True,
            ).exists():
                raise ValidationError({
                    "organization_id": "The selected client must already belong to this organization."
                })
        else:
            organization = OrganizationService.create(
                name=validated_data.pop("organization_name", ""),
                owner=customer,
                billing_email=validated_data["customer_email"],
                created_by=actor,
            )

        if organization.status != Organization.Status.ACTIVE:
            raise ValidationError({"organization_id": "Draft organizations cannot receive orders or payments."})

        normalized_organization, normalized_items, _ = CartLicenseService.normalize_checkout_items(
            user=customer,
            items=items,
            organization_id=organization.pk,
            lock=True,
        )
        if normalized_organization != organization:
            raise ValidationError({"organization_id": "The selected organization could not be verified."})

        initial_status = Order.Status.DRAFT if payment_state == "draft" else Order.Status.PENDING
        order = OrderService.create_order(
            validated_data={
                **validated_data,
                "organization": organization,
                "status": initial_status,
                "created_by": actor,
                "items": [
                    {"product": product, "quantity": quantity}
                    for product, quantity in normalized_items
                ],
            },
            user=actor,
        )

        if payment_state == "paid":
            provider = PaymentProvider.objects.filter(
                code=PaymentProvider.Code.BANK_TRANSFER,
                is_enabled=True,
            ).first()
            if provider is None:
                raise ValidationError({"payment_state": "Enable the Bank transfer payment provider first."})
            attempt = PaymentAttempt.objects.create(
                order=order,
                provider=provider,
                amount=order.total,
                currency="USD",
                status=PaymentAttempt.Status.PENDING,
                is_test=provider.test_mode,
                metadata={"source": "admin_manual_order", "verified_by": actor.pk},
                created_by=actor,
            )
            PaymentService.record_attempt_created(attempt=attempt, actor=actor)
            PaymentService.complete_success(
                attempt=attempt,
                actor=actor,
                external_reference=payment_reference or f"ADMIN-{uuid4().hex[:12].upper()}",
            )
            order.refresh_from_db()
        return order
