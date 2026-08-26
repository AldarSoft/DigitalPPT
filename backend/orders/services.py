from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from orders.models import InventoryReservation, Order, OrderItem
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
        pending_items = [item for item in physical_items if item.pk not in existing]
        if not pending_items:
            return list(existing.values())

        reserved = InventoryReservationService.reserved_quantities(product_ids=product_ids)
        required = {}
        for item in pending_items:
            required[item.product_id] = required.get(item.product_id, 0) + item.quantity

        stock_errors = {}
        for product_id, quantity in required.items():
            product = products.get(product_id)
            available = InventoryReservationService.available_quantity(
                product=product,
                reserved_quantity=reserved.get(product_id, 0),
            ) if product else 0
            if available < quantity:
                stock_errors[str(product_id)] = (
                    f"Only {available} units are available to reserve; {quantity} requested."
                )
        if stock_errors:
            raise ValidationError({"inventory": stock_errors})

        created = InventoryReservation.objects.bulk_create([
            InventoryReservation(order_item=item, product=products[item.product_id], quantity=item.quantity)
            for item in pending_items
        ])
        return [*existing.values(), *created]

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
        InventoryReservation.objects.filter(pk__in=[reservation.pk for reservation in reservations]).update(
            status=InventoryReservation.Status.CONSUMED,
            consumed_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return True

    @staticmethod
    def release_for_order(*, order, reason):
        return InventoryReservation.objects.filter(
            order_item__order=order,
            status=InventoryReservation.Status.RESERVED,
        ).update(
            status=InventoryReservation.Status.RELEASED,
            released_at=timezone.now(),
            release_reason=reason[:255],
            updated_at=timezone.now(),
        )


class OrderService:
    ALLOWED_STATUS_TRANSITIONS = {
        Order.Status.DRAFT: {
            Order.Status.PENDING,
            Order.Status.CANCELLED,
        },
        Order.Status.PENDING: {
            Order.Status.SCHEDULED,
            Order.Status.PROCESSING,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        },
        Order.Status.PROCESSING: {
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        },
        Order.Status.SCHEDULED: {
            Order.Status.PROCESSING,
            Order.Status.COMPLETED,
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
        if not actor or not actor.is_staff:
            raise ValidationError({"detail": "Administrator access is required."})

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
            PaymentService.complete_success(
                attempt=attempt,
                actor=actor,
                external_reference=payment_reference or f"ADMIN-{uuid4().hex[:12].upper()}",
            )
            order.refresh_from_db()
        return order
