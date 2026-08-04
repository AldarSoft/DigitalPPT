from __future__ import annotations

import logging

from django.db import transaction
from rest_framework.exceptions import ValidationError

from quotes.models import QuoteRequest, QuoteRequestItem

logger = logging.getLogger(__name__)


class QuoteService:
    ALLOWED_STATUS_TRANSITIONS = {
        QuoteRequest.Status.NEW: {QuoteRequest.Status.REVIEWING, QuoteRequest.Status.CLOSED},
        QuoteRequest.Status.REVIEWING: {QuoteRequest.Status.QUOTED, QuoteRequest.Status.CLOSED},
        QuoteRequest.Status.QUOTED: {QuoteRequest.Status.APPROVED, QuoteRequest.Status.CLOSED},
        QuoteRequest.Status.APPROVED: set(),
        QuoteRequest.Status.CLOSED: set(),
    }

    @staticmethod
    @transaction.atomic
    def create_quote_request(*, validated_data, user=None):
        items_data = validated_data.pop("items")
        authenticated_user = user if user and user.is_authenticated else None
        quote_request = QuoteRequest.objects.create(user=authenticated_user, **validated_data)

        QuoteRequestItem.objects.bulk_create(
            [
                QuoteRequestItem(
                    quote_request=quote_request,
                    product=item["product"],
                    product_name=item["product"].name,
                    sku=item["product"].sku,
                    quantity=item["quantity"],
                    specifications=item.get("specifications", {}),
                )
                for item in items_data
            ]
        )

        from core.notifications import publish_quote_created

        transaction.on_commit(
            lambda quote_id=quote_request.pk: publish_quote_created(quote_id)
        )

        logger.info(
            "Created quote request %s with %s items",
            quote_request.quote_number,
            len(items_data),
        )
        return (
            QuoteRequest.objects.prefetch_related("items__product", "orders")
            .get(pk=quote_request.pk)
        )

    @staticmethod
    @transaction.atomic
    def update_status(*, quote_request, new_status, user=None):
        quote_request = (
            QuoteRequest.objects.select_for_update()
            .prefetch_related("items__product", "orders")
            .get(pk=quote_request.pk)
        )
        if quote_request.status == new_status:
            return quote_request

        allowed = QuoteService.ALLOWED_STATUS_TRANSITIONS[quote_request.status]
        if new_status not in allowed:
            raise ValidationError(
                {"status": f"Cannot change a {quote_request.status} quote to {new_status}."}
            )

        if new_status == QuoteRequest.Status.APPROVED:
            QuoteService._create_order_from_quote(quote_request=quote_request, user=user)

        quote_request.status = new_status
        quote_request.save(update_fields=["status", "updated_at"])
        return quote_request

    @staticmethod
    def _create_order_from_quote(*, quote_request, user=None):
        existing_order = quote_request.orders.order_by("created_at", "id").first()
        if existing_order:
            return existing_order

        items = list(quote_request.items.select_related("product"))
        unavailable = [item.product_name for item in items if item.product is None]
        if unavailable:
            raise ValidationError(
                {"status": "Cannot approve a quote containing unavailable products."}
            )

        from orders.services import OrderService

        contact_parts = quote_request.requester_contact_person.strip().split(maxsplit=1)
        first_name = contact_parts[0]
        last_name = contact_parts[1] if len(contact_parts) > 1 else ""
        return OrderService.create_order(
            validated_data={
                "quote_request": quote_request,
                "customer_first_name": first_name,
                "customer_last_name": last_name,
                "customer_email": quote_request.requester_email,
                "customer_phone": quote_request.requester_phone,
                "company_name": quote_request.requester_company_name,
                "shipping_address": "",
                "shipping_city": "",
                "shipping_state": "",
                "shipping_postal_code": "",
                "shipping_country": "",
                "notes": quote_request.notes,
                "items": [
                    {
                        "product": item.product,
                        "product_name": item.product_name,
                        "sku": item.sku,
                        "quantity": item.quantity,
                    }
                    for item in items
                ],
            },
            user=user,
        )
