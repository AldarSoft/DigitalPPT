from __future__ import annotations

import logging
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import ValidationError

from orders.models import Order, OrderItem
from products.models import Product

logger = logging.getLogger(__name__)


class OrderService:
    ALLOWED_STATUS_TRANSITIONS = {
        Order.Status.PENDING: {
            Order.Status.PROCESSING,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        },
        Order.Status.PROCESSING: {
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
        authenticated_user = user if user and user.is_authenticated else None
        order_user = authenticated_user

        if authenticated_user and authenticated_user.is_staff:
            User = get_user_model()
            order_user = quote_request.user if quote_request and quote_request.user else (
                User.objects.filter(email__iexact=validated_data.get("customer_email")).first()
                or authenticated_user
            )

        order = Order.objects.create(
            user=order_user,
            quote_request=quote_request,
            **validated_data,
        )

        subtotal = Decimal("0.00")
        order_items = []
        for item_data in items_data:
            product = item_data.get("product")
            unit_price = item_data.get("unit_price") or (
                product.current_price if product else Decimal("0.00")
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
        order.tax_amount = Decimal("0.00")
        order.shipping_fee = Decimal("0.00")
        order.total = subtotal
        order.save(update_fields=["subtotal", "tax_amount", "shipping_fee", "total", "updated_at"])

        logger.info("Created order %s with %s items", order.order_number, len(order_items))
        return (
            Order.objects.select_related("user")
            .prefetch_related("items__product")
            .get(pk=order.pk)
        )

    @staticmethod
    @transaction.atomic
    def create_checkout_order(*, validated_data, user=None):
        items_data = validated_data.pop("items")
        authenticated_user = user if user and user.is_authenticated else None
        product_ids = [item["product"].pk for item in items_data]
        products = Product.objects.select_for_update().public().in_bulk(product_ids)

        subtotal = Decimal("0.00")
        prepared_items = []
        inventory_errors = {}
        for item in items_data:
            product = products.get(item["product"].pk)
            quantity = item["quantity"]
            if not product:
                raise ValidationError({"items": "A product is no longer available."})
            if product.inventory_quantity < quantity:
                inventory_errors[str(product.pk)] = (
                    f"Only {product.inventory_quantity} units are available."
                )
                continue
            line_total = product.current_price * quantity
            subtotal += line_total
            prepared_items.append(
                OrderItem(
                    product=product,
                    product_name=product.name,
                    sku=product.sku,
                    unit_price=product.current_price,
                    quantity=quantity,
                    line_total=line_total,
                )
            )

        if inventory_errors:
            raise ValidationError({"inventory": inventory_errors})

        order = Order.objects.create(user=authenticated_user, **validated_data)
        for item in prepared_items:
            item.order = order
        OrderItem.objects.bulk_create(prepared_items)
        order.subtotal = subtotal
        order.total = subtotal
        order.save(update_fields=["subtotal", "total", "updated_at"])
        logger.info("Created checkout order %s", order.order_number)
        return (
            Order.objects.select_related("user")
            .prefetch_related("items__product")
            .get(pk=order.pk)
        )

    @staticmethod
    @transaction.atomic
    def update_status(*, order, new_status):
        locked_order = (
            Order.objects.select_for_update()
            .prefetch_related("items__product")
            .get(pk=order.pk)
        )
        if new_status == locked_order.status:
            return locked_order

        previous_status = locked_order.status

        allowed = OrderService.ALLOWED_STATUS_TRANSITIONS.get(locked_order.status, set())
        if new_status not in allowed:
            raise ValidationError(
                {"status": f"Cannot change order from {locked_order.status} to {new_status}."}
            )

        item_quantities = {}
        for item in locked_order.items.all():
            if item.product_id:
                item_quantities[item.product_id] = (
                    item_quantities.get(item.product_id, 0) + item.quantity
                )

        should_deduct = (
            new_status in {Order.Status.PROCESSING, Order.Status.COMPLETED}
            and not locked_order.stock_deducted
        )
        should_restore = (
            new_status == Order.Status.CANCELLED and locked_order.stock_deducted
        )

        if should_deduct and item_quantities:
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

        locked_order.status = new_status
        locked_order.save(update_fields=["status", "stock_deducted", "updated_at"])

        from core.notifications import publish_order_status_changed

        transaction.on_commit(
            lambda order_id=locked_order.pk, old=previous_status, new=new_status:
            publish_order_status_changed(order_id, old, new)
        )
        return locked_order
