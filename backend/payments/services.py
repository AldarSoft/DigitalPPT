from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.models import SiteSetting
from orders.models import Order
from orders.services import OrderService
from payments.models import PaymentAttempt
from payments.providers import provider_is_available


class PaymentService:
    @staticmethod
    def close_pending_attempts(*, order, exclude_attempt_id=None, reason):
        attempts = PaymentAttempt.objects.filter(
            order=order,
            status=PaymentAttempt.Status.PENDING,
        )
        if exclude_attempt_id is not None:
            attempts = attempts.exclude(pk=exclude_attempt_id)
        return attempts.update(
            status=PaymentAttempt.Status.CANCELLED,
            failure_message=reason,
            updated_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def start_checkout(*, user, order, provider, idempotency_key, billing):
        existing = (
            PaymentAttempt.objects.select_for_update()
            .select_related("order", "provider", "created_by")
            .filter(idempotency_key=idempotency_key)
            .first()
        )
        if existing:
            if (
                existing.created_by_id != user.id
                or existing.order_id != order.id
                or existing.provider_id != provider.id
            ):
                raise ValidationError({"idempotency_key": "This key is already in use."})
            return existing, False

        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if not user.is_staff and locked_order.user_id != user.id:
            raise ValidationError({"order_number": "This order is not available."})
        if locked_order.status != Order.Status.PENDING:
            raise ValidationError({"order_number": "Only pending orders can be paid."})
        if locked_order.total <= 0:
            raise ValidationError({"order_number": "The order total must be greater than zero."})
        if PaymentAttempt.objects.filter(
            order=locked_order,
            status=PaymentAttempt.Status.SUCCEEDED,
        ).exists():
            raise ValidationError({"order_number": "This order is already paid."})
        if not provider_is_available(provider):
            raise ValidationError({"provider": "This payment provider is unavailable."})

        PaymentService.close_pending_attempts(
            order=locked_order,
            reason="Replaced by a newer checkout session.",
        )

        if not user.is_staff:
            locked_order.customer_email = billing["email"]
            locked_order.customer_first_name = billing["first_name"]
            locked_order.customer_last_name = billing["last_name"]
            locked_order.customer_phone = billing.get("phone", "")
            locked_order.company_name = billing.get("company", "")
            locked_order.shipping_address = billing["address"]
            locked_order.shipping_city = billing["city"]
            locked_order.shipping_state = billing.get("state", "")
            locked_order.shipping_postal_code = billing["postal_code"]
            locked_order.shipping_country = billing["country"]
            locked_order.save(update_fields=[
                "customer_email", "customer_first_name", "customer_last_name",
                "customer_phone", "company_name", "shipping_address", "shipping_city",
                "shipping_state", "shipping_postal_code", "shipping_country", "updated_at",
            ])

        site_settings = SiteSetting.get_solo()
        attempt = PaymentAttempt.objects.create(
            order=locked_order,
            provider=provider,
            amount=locked_order.total,
            currency=site_settings.default_currency or "USD",
            status=PaymentAttempt.Status.PENDING,
            is_test=provider.test_mode,
            idempotency_key=idempotency_key,
            expires_at=timezone.now() + timedelta(minutes=settings.PAYMENT_SESSION_TTL_MINUTES),
            metadata={"source": "storefront", "billing": billing},
            created_by=user,
        )
        return attempt, True

    @staticmethod
    @transaction.atomic
    def create_admin_simulation(*, user, order, provider, outcome):
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status != Order.Status.PENDING:
            raise ValidationError({"order_number": "Only pending orders can be paid."})
        if locked_order.total <= 0:
            raise ValidationError({"order_number": "The order total must be greater than zero."})
        if PaymentAttempt.objects.filter(
            order=locked_order,
            status=PaymentAttempt.Status.SUCCEEDED,
        ).exists():
            raise ValidationError({"order_number": "This order is already paid."})

        PaymentService.close_pending_attempts(
            order=locked_order,
            reason="Replaced by an admin payment simulation.",
        )
        attempt = PaymentAttempt.objects.create(
            order=locked_order,
            provider=provider,
            amount=locked_order.total,
            currency="USD",
            status=PaymentAttempt.Status.PENDING,
            is_test=True,
            expires_at=timezone.now() + timedelta(minutes=settings.PAYMENT_SESSION_TTL_MINUTES),
            metadata={"source": "admin_simulation"},
            created_by=user,
        )
        if outcome == PaymentAttempt.Status.PENDING:
            return attempt
        return PaymentService.simulate_checkout(
            attempt=attempt,
            user=user,
            outcome=outcome,
        )

    @staticmethod
    @transaction.atomic
    def refresh_attempt(*, attempt):
        locked = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if (
            locked.status == PaymentAttempt.Status.PENDING
            and locked.expires_at
            and locked.expires_at <= timezone.now()
        ):
            locked.status = PaymentAttempt.Status.EXPIRED
            locked.failure_message = "The checkout session expired."
            locked.save(update_fields=["status", "failure_message", "updated_at"])
        return locked

    @staticmethod
    @transaction.atomic
    def simulate_checkout(*, attempt, user, outcome):
        locked = (
            PaymentAttempt.objects.select_for_update()
            .select_related("order", "provider", "created_by")
            .get(pk=attempt.pk)
        )
        if not user.is_staff and locked.created_by_id != user.id:
            raise ValidationError({"session": "This payment session is not available."})
        if locked.status != PaymentAttempt.Status.PENDING:
            return locked
        if locked.expires_at and locked.expires_at <= timezone.now():
            locked.status = PaymentAttempt.Status.EXPIRED
            locked.failure_message = "The development checkout session expired."
            locked.save(update_fields=["status", "failure_message", "updated_at"])
            return locked

        if outcome == PaymentAttempt.Status.FAILED:
            locked.status = PaymentAttempt.Status.FAILED
            locked.failure_message = "Simulated provider decline."
            locked.external_reference = f"dev_failed_{locked.pk}"
            locked.save(update_fields=["status", "failure_message", "external_reference", "updated_at"])
            return locked

        locked_order = Order.objects.select_for_update().get(pk=locked.order_id)
        another_success = PaymentAttempt.objects.filter(
            order=locked_order,
            status=PaymentAttempt.Status.SUCCEEDED,
        ).exclude(pk=locked.pk).exists()
        if another_success or locked_order.status != Order.Status.PENDING:
            locked.status = PaymentAttempt.Status.CANCELLED
            locked.failure_message = (
                "The order was already paid or is no longer awaiting payment."
            )
            locked.save(update_fields=["status", "failure_message", "updated_at"])
            return locked

        next_status = (
            Order.Status.SCHEDULED
            if locked_order.source == Order.Source.QUOTE
            else Order.Status.PROCESSING
        )
        OrderService.update_status(order=locked_order, new_status=next_status)
        locked.status = PaymentAttempt.Status.SUCCEEDED
        locked.failure_message = ""
        locked.external_reference = f"dev_paid_{locked.pk}"
        locked.paid_at = timezone.now()
        locked.save(update_fields=["status", "failure_message", "external_reference", "paid_at", "updated_at"])
        PaymentService.close_pending_attempts(
            order=locked_order,
            exclude_attempt_id=locked.pk,
            reason="Closed after another payment succeeded.",
        )
        locked.order.refresh_from_db(fields=["status"])
        return locked
