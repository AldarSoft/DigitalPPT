from __future__ import annotations

import logging
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from quotes.models import QuoteMessage, QuoteRequest, QuoteRequestItem

logger = logging.getLogger(__name__)


class QuoteService:
    ALLOWED_STATUS_TRANSITIONS = {
        QuoteRequest.Status.NEW: {QuoteRequest.Status.REVIEWING, QuoteRequest.Status.CANCELLED},
        QuoteRequest.Status.REVIEWING: {
            QuoteRequest.Status.QUOTE_APPROVED,
            QuoteRequest.Status.CANCELLED,
        },
        QuoteRequest.Status.QUOTE_APPROVED: {QuoteRequest.Status.CANCELLED},
        QuoteRequest.Status.INVOICE_SENT: set(),
        QuoteRequest.Status.AWAITING_PAYMENT: set(),
        QuoteRequest.Status.PAYMENT_CONFIRMED: set(),
        QuoteRequest.Status.PAYMENT_REJECTED: set(),
        QuoteRequest.Status.CANCELLED: set(),
    }

    @staticmethod
    def _queryset():
        return QuoteRequest.objects.select_related("renewal_license").prefetch_related(
            "items__product", "orders", "messages__author"
        )

    @staticmethod
    @transaction.atomic
    def create_quote_request(*, validated_data, user=None):
        items_data = validated_data.pop("items")
        authenticated_user = (
            user if user and user.is_authenticated and not user.is_staff else None
        )
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
        return QuoteService._queryset().get(pk=quote_request.pk)

    @staticmethod
    @transaction.atomic
    def claim_guest_quote(*, quote_request, user, token: str):
        from orders.models import Order
        from quotes.claims import validate_guest_quote_claim_token

        locked = QuoteService._queryset().select_for_update().get(pk=quote_request.pk)
        validate_guest_quote_claim_token(quote_request=locked, token=token)

        if locked.requester_email.lower() != user.email.lower():
            raise ValidationError({"token": "Sign in with the email address that received this quote link."})
        if locked.user_id and locked.user_id != user.pk:
            raise ValidationError({"token": "This quote has already been claimed by another account."})

        if locked.user_id != user.pk:
            locked.user = user
            locked.save(update_fields=["user", "updated_at"])

            # A legacy guest quote may already have been invoiced by staff. Only
            # transfer its linked order when the order itself names this claimant.
            Order.objects.filter(
                quote_request=locked,
                customer_email__iexact=user.email,
            ).filter(Q(user__isnull=True) | Q(user__is_staff=True)).update(user=user)

        return QuoteService._queryset().get(pk=locked.pk)

    @staticmethod
    @transaction.atomic
    def update_status(*, quote_request, new_status, user=None):
        quote_request = QuoteService._queryset().select_for_update().get(pk=quote_request.pk)
        if quote_request.status == new_status:
            return quote_request

        allowed = QuoteService.ALLOWED_STATUS_TRANSITIONS[quote_request.status]
        if new_status not in allowed:
            raise ValidationError(
                {"status": f"Cannot change a {quote_request.status} quote to {new_status}."}
            )

        QuoteService._set_status(quote_request=quote_request, new_status=new_status)
        return quote_request

    @staticmethod
    def _set_status(*, quote_request, new_status):
        if quote_request.status == new_status:
            return quote_request
        previous_status = quote_request.status
        quote_request.status = new_status
        quote_request.save(update_fields=["status", "updated_at"])
        from core.notifications import publish_quote_status_changed

        transaction.on_commit(
            lambda quote_id=quote_request.pk, old=previous_status, new=new_status:
            publish_quote_status_changed(quote_id, old, new)
        )
        return quote_request

    @staticmethod
    @transaction.atomic
    def mark_invoice_awaiting_payment(*, quote_id):
        quote_request = QuoteRequest.objects.select_for_update().get(pk=quote_id)
        if quote_request.status != QuoteRequest.Status.INVOICE_SENT:
            return quote_request
        return QuoteService._set_status(
            quote_request=quote_request,
            new_status=QuoteRequest.Status.AWAITING_PAYMENT,
        )

    @staticmethod
    @transaction.atomic
    def mark_payment_rejected(*, quote_request, reason):
        locked = QuoteRequest.objects.select_for_update().get(pk=quote_request.pk)
        if locked.status not in {
            QuoteRequest.Status.INVOICE_SENT,
            QuoteRequest.Status.AWAITING_PAYMENT,
            QuoteRequest.Status.PAYMENT_REJECTED,
        }:
            raise ValidationError({"status": "This quote is not awaiting a bank payment."})
        previous_status = locked.status
        locked.status = QuoteRequest.Status.PAYMENT_REJECTED
        locked.payment_rejection_reason = reason.strip()
        locked.save(update_fields=["status", "payment_rejection_reason", "updated_at"])
        if previous_status != QuoteRequest.Status.PAYMENT_REJECTED:
            from core.notifications import publish_quote_status_changed

            transaction.on_commit(
                lambda quote_id=locked.pk, old=previous_status:
                publish_quote_status_changed(
                    quote_id,
                    old,
                    QuoteRequest.Status.PAYMENT_REJECTED,
                )
            )
        return locked

    @staticmethod
    def _apply_pricing(*, locked, item_prices, shipping, admin_message, updated_at):
        items = list(locked.items.all())
        prices_by_id = {item["id"]: item["quoted_unit_price"] for item in item_prices}
        if set(prices_by_id) != {item.id for item in items}:
            raise ValidationError({"items": "Provide a price for every requested item."})

        subtotal = Decimal("0.00")
        for item in items:
            unit_price = prices_by_id[item.id]
            if unit_price <= 0:
                raise ValidationError({"items": "Quoted prices must be greater than zero."})
            item.quoted_unit_price = unit_price
            item.quoted_line_total = unit_price * item.quantity
            item.updated_at = updated_at
            subtotal += item.quoted_line_total
        QuoteRequestItem.objects.bulk_update(
            items, ["quoted_unit_price", "quoted_line_total", "updated_at"]
        )

        locked.admin_message = admin_message
        locked.quoted_subtotal = subtotal
        locked.quoted_shipping = shipping
        locked.quoted_total = subtotal + shipping
        locked.quoted_at = updated_at
        locked.save(update_fields=[
            "admin_message", "quoted_subtotal", "quoted_shipping", "quoted_total",
            "quoted_at", "updated_at",
        ])

    @staticmethod
    @transaction.atomic
    def add_message(*, quote_request, user, body):
        locked = QuoteRequest.objects.select_for_update().get(pk=quote_request.pk)
        if locked.status not in {
            QuoteRequest.Status.REVIEWING,
            QuoteRequest.Status.QUOTE_APPROVED,
            QuoteRequest.Status.INVOICE_SENT,
            QuoteRequest.Status.AWAITING_PAYMENT,
            QuoteRequest.Status.PAYMENT_REJECTED,
        }:
            raise ValidationError({"status": "Messages are available while a quote is being negotiated or awaiting payment."})
        sender_role = (
            QuoteMessage.SenderRole.ADMIN
            if user.is_staff
            else QuoteMessage.SenderRole.CUSTOMER
        )
        message = QuoteMessage.objects.create(
            quote_request=locked,
            author=user,
            sender_role=sender_role,
            body=body.strip(),
        )
        locked.save(update_fields=["updated_at"])
        from django.contrib.auth import get_user_model
        from core.models import UserNotification

        User = get_user_model()
        if sender_role == QuoteMessage.SenderRole.CUSTOMER:
            recipient_ids = User.objects.filter(
                is_staff=True,
                is_active=True,
            ).values_list("pk", flat=True)
            title = f"New message on {locked.quote_number}"
            url = f"/admin/quotes?quote={locked.quote_number}"
        else:
            recipient_ids = (
                [locked.user_id]
                if locked.user_id and locked.user_id != user.pk
                else []
            )
            title = f"Quote update: {locked.quote_number}"
            url = f"/account?tab=quotes&quote={locked.quote_number}"

        UserNotification.objects.bulk_create([
            UserNotification(
                recipient_id=recipient_id,
                title=title,
                message=body.strip(),
                url=url,
            )
            for recipient_id in recipient_ids
        ])

        from core.notifications import publish_quote_message

        transaction.on_commit(
            lambda message_id=message.pk: publish_quote_message(message_id)
        )
        return QuoteService._queryset().get(pk=locked.pk)

    @staticmethod
    @transaction.atomic
    def issue_invoice(*, quote_request, user, item_prices, shipping, admin_message):
        locked = QuoteService._queryset().select_for_update().get(pk=quote_request.pk)
        allowed_statuses = {
            QuoteRequest.Status.QUOTE_APPROVED,
            QuoteRequest.Status.INVOICE_SENT,
            QuoteRequest.Status.AWAITING_PAYMENT,
            QuoteRequest.Status.PAYMENT_REJECTED,
        }
        if locked.status not in allowed_statuses:
            raise ValidationError({"status": "Approve the quote before issuing its invoice."})
        from core.models import SiteSetting
        from orders.models import Order
        from payments.models import PaymentAttempt
        from payments.services import PaymentService
        from quotes.invoice_pdf import build_invoice_pdf

        now = timezone.now()
        previous_status = locked.status
        existing_order = locked.orders.select_for_update().order_by("created_at", "id").first()
        if existing_order:
            if existing_order.status != Order.Status.PENDING or existing_order.stock_deducted:
                raise ValidationError({"status": "This invoice can no longer be changed because its order is already being processed."})
            expired_attempts = PaymentAttempt.objects.select_for_update().filter(
                order=existing_order,
                status=PaymentAttempt.Status.PENDING,
                expires_at__lte=now,
            )
            for attempt in expired_attempts:
                PaymentService.mark_pending_terminal(
                    attempt=attempt,
                    terminal_status=PaymentAttempt.Status.EXPIRED,
                    reason="The checkout session expired before the invoice was revised.",
                )
            if PaymentAttempt.objects.filter(
                order=existing_order,
                status__in={PaymentAttempt.Status.PENDING, PaymentAttempt.Status.SUCCEEDED},
            ).exists():
                raise ValidationError({"status": "This invoice cannot be changed while a payment session is active."})

        QuoteService._apply_pricing(
            locked=locked,
            item_prices=item_prices,
            shipping=shipping,
            admin_message=admin_message,
            updated_at=now,
        )
        locked.invoice_number = locked.invoice_number or f"INV-{now.year}-{locked.pk:06d}"
        locked.invoiced_at = now
        locked.status = QuoteRequest.Status.INVOICE_SENT
        locked.payment_rejection_reason = ""
        locked.save(update_fields=[
            "invoice_number", "invoiced_at", "status", "payment_rejection_reason",
            "updated_at",
        ])
        pdf = build_invoice_pdf(
            quote_request=locked,
            site_settings=SiteSetting.get_solo(),
        )
        if locked.invoice_pdf:
            locked.invoice_pdf.delete(save=False)
        locked.invoice_pdf.save(
            f"{locked.invoice_number}.pdf",
            ContentFile(pdf),
            save=True,
        )
        QuoteService._create_or_update_order_from_quote(
            quote_request=locked,
            user=user,
            existing_order=existing_order,
        )

        from core.notifications import publish_quote_ready

        transaction.on_commit(lambda quote_id=locked.pk: publish_quote_ready(quote_id))
        from core.notifications import publish_quote_status_changed

        transaction.on_commit(
            lambda quote_id=locked.pk, old=previous_status:
            publish_quote_status_changed(quote_id, old, QuoteRequest.Status.INVOICE_SENT)
        )
        return QuoteService._queryset().get(pk=locked.pk)

    @staticmethod
    def _create_or_update_order_from_quote(*, quote_request, user=None, existing_order=None):
        items = list(quote_request.items.select_related("product"))
        unavailable = [item.product_name for item in items if item.product is None]
        if unavailable:
            raise ValidationError(
                {"status": "Cannot invoice a quote containing unavailable products."}
            )

        from orders.models import OrderItem
        from orders.services import OrderService

        if existing_order:
            existing_order.items.all().delete()
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=existing_order,
                    product=item.product,
                    product_name=item.product_name,
                    sku=item.sku,
                    quantity=item.quantity,
                    unit_price=item.quoted_unit_price,
                    line_total=item.quoted_line_total,
                )
                for item in items
            ])
            existing_order.subtotal = quote_request.quoted_subtotal
            existing_order.shipping_fee = quote_request.quoted_shipping
            existing_order.tax_amount = Decimal("0.00")
            existing_order.total = quote_request.quoted_total
            existing_order.notes = quote_request.notes
            existing_order.renewal_license = quote_request.renewal_license
            if quote_request.renewal_license_id:
                existing_order.organization = quote_request.renewal_license.organization
            existing_order.save(update_fields=[
                "subtotal", "shipping_fee", "tax_amount", "total", "notes", "renewal_license", "organization", "updated_at",
            ])
            return existing_order

        contact_parts = quote_request.requester_contact_person.strip().split(maxsplit=1)
        first_name = contact_parts[0]
        last_name = contact_parts[1] if len(contact_parts) > 1 else ""
        return OrderService.create_order(
            validated_data={
                "quote_request": quote_request,
                "renewal_license": quote_request.renewal_license,
                "organization": (
                    quote_request.renewal_license.organization
                    if quote_request.renewal_license_id
                    else None
                ),
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
                "shipping_fee": quote_request.quoted_shipping,
                "items": [
                    {
                        "product": item.product,
                        "product_name": item.product_name,
                        "sku": item.sku,
                        "quantity": item.quantity,
                        "unit_price": item.quoted_unit_price,
                    }
                    for item in items
                ],
            },
            user=quote_request.user or user,
        )
