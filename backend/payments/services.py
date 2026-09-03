from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.models import SiteSetting
from orders.models import Order
from orders.services import InventoryReservationService, OrderService
from payments.models import (
    PaymentAttempt,
    PaymentProvider,
    PaymentProviderEvent,
    PaymentStatusEvent,
)
from payments.providers import get_provider_adapter, provider_is_available


security_logger = logging.getLogger("security.payments")


class PaymentService:
    @staticmethod
    def _record_status_event(
        *,
        attempt,
        event_type,
        previous_status,
        actor=None,
        reason="",
        metadata=None,
    ):
        quote_request = attempt.order.quote_request if attempt.order_id else None
        return PaymentStatusEvent.objects.create(
            payment_attempt=attempt,
            event_type=event_type,
            previous_status=previous_status,
            new_status=attempt.status,
            invoice_reference=(quote_request.invoice_number or "") if quote_request else "",
            amount=attempt.amount,
            currency=attempt.currency,
            external_reference=attempt.external_reference,
            reason=reason,
            actor=actor,
            metadata=metadata or {},
        )

    @staticmethod
    def record_attempt_created(*, attempt, actor=None):
        return PaymentService._record_status_event(
            attempt=attempt,
            event_type=PaymentStatusEvent.EventType.ATTEMPT_CREATED,
            previous_status=attempt.status,
            actor=actor,
            reason="Payment attempt created.",
        )

    @staticmethod
    def attach_provider_checkout(*, attempt):
        """Persist the provider session created by a registered live adapter."""
        if attempt.is_test:
            return attempt
        adapter = get_provider_adapter(attempt.provider.code)
        if not adapter:
            raise ValidationError({"provider": "This payment provider is unavailable."})
        session = adapter.create_checkout(attempt=attempt)
        metadata = dict(attempt.metadata or {})
        metadata["checkout_url"] = session.checkout_url
        metadata["provider_session"] = session.metadata
        attempt.external_reference = session.external_reference[:255]
        attempt.metadata = metadata
        attempt.save(update_fields=["external_reference", "metadata", "updated_at"])
        return attempt

    @staticmethod
    def can_pay_order(*, user, order):
        if not user or not user.is_authenticated:
            return False
        if order.user_id == user.id:
            return True
        if user.is_staff:
            return user.is_superuser or user.has_perm("users.confirm_bank_payments")
        if not order.organization_id:
            return False
        from licensing.permissions import OrganizationAccessPolicy

        return OrganizationAccessPolicy.can_pay_orders(
            user=user,
            organization=order.organization,
        )

    @staticmethod
    def can_pay_attempt(*, user, attempt):
        if attempt.order_id:
            return PaymentService.can_pay_order(user=user, order=attempt.order)
        if not attempt.renewal_license_id:
            return False
        from licensing.permissions import OrganizationAccessPolicy

        return OrganizationAccessPolicy.can_manage_billing(
            user=user,
            organization=attempt.renewal_license.organization,
        )

    @staticmethod
    @transaction.atomic
    def close_pending_attempts(*, order, exclude_attempt_id=None, reason):
        attempts = PaymentAttempt.objects.select_for_update().select_related(
            "order__quote_request"
        ).filter(
            order=order,
            status=PaymentAttempt.Status.PENDING,
        )
        if exclude_attempt_id is not None:
            attempts = attempts.exclude(pk=exclude_attempt_id)
        count = 0
        for attempt in attempts:
            previous_status = attempt.status
            attempt.status = PaymentAttempt.Status.CANCELLED
            attempt.failure_message = reason
            attempt.save(update_fields=["status", "failure_message", "updated_at"])
            PaymentService._record_status_event(
                attempt=attempt,
                event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
                previous_status=previous_status,
                reason=reason,
            )
            count += 1
        return count

    @staticmethod
    @transaction.atomic
    def close_pending_renewal_attempts(
        *,
        renewal_license,
        exclude_attempt_id=None,
        reason,
    ):
        attempts = PaymentAttempt.objects.select_for_update().select_related(
            "order__quote_request"
        ).filter(
            renewal_license=renewal_license,
            status=PaymentAttempt.Status.PENDING,
        )
        if exclude_attempt_id is not None:
            attempts = attempts.exclude(pk=exclude_attempt_id)
        count = 0
        for attempt in attempts:
            previous_status = attempt.status
            attempt.status = PaymentAttempt.Status.CANCELLED
            attempt.failure_message = reason
            attempt.save(update_fields=["status", "failure_message", "updated_at"])
            PaymentService._record_status_event(
                attempt=attempt,
                event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
                previous_status=previous_status,
                reason=reason,
            )
            count += 1
        return count

    @staticmethod
    @transaction.atomic
    def confirm_bank_transfer(*, order, actor, bank_transaction_reference, internal_note=""):
        """Record a staff-verified transfer and run the standard success workflow."""
        if not actor or not actor.is_staff or not (
            actor.is_superuser or actor.has_perm("users.confirm_bank_payments")
        ):
            raise ValidationError({"detail": "Finance payment confirmation access is required."})

        locked_order = (
            Order.objects.select_for_update()
            .select_related("quote_request")
            .get(pk=order.pk)
        )
        if not locked_order.quote_request_id:
            raise ValidationError({"order": "Manual bank confirmation is available for quote invoices only."})
        quote_request = locked_order.quote_request
        if quote_request.status not in {
            quote_request.Status.INVOICE_SENT,
            quote_request.Status.AWAITING_PAYMENT,
            quote_request.Status.PAYMENT_REJECTED,
        } or not quote_request.invoice_number:
            raise ValidationError({"order": "This quote does not have an invoice awaiting payment."})
        if quote_request.quoted_total is None or quote_request.quoted_total != locked_order.total:
            raise ValidationError({"order": "The invoice amount does not match the order total."})
        if locked_order.status != Order.Status.PENDING:
            raise ValidationError({"order": "Only orders awaiting payment can be confirmed."})
        if PaymentAttempt.objects.filter(order=locked_order, status=PaymentAttempt.Status.SUCCEEDED).exists():
            raise ValidationError({"order": "This order is already paid."})

        provider = PaymentProvider.objects.select_for_update().filter(
            code=PaymentProvider.Code.BANK_TRANSFER,
            is_enabled=True,
        ).first()
        if not provider:
            raise ValidationError({"provider": "Enable the Bank transfer provider before confirming payment."})

        bank_transaction_reference = bank_transaction_reference.strip().upper()
        if PaymentAttempt.objects.filter(
            provider=provider,
            external_reference=bank_transaction_reference,
            status=PaymentAttempt.Status.SUCCEEDED,
        ).exists():
            security_logger.warning(
                "Duplicate bank reference blocked for order_id=%s actor_id=%s",
                locked_order.pk,
                actor.pk,
            )
            raise ValidationError({
                "bank_transaction_reference": (
                    "This bank transaction reference was already confirmed for another payment."
                )
            })

        attempt = PaymentAttempt.objects.create(
            order=locked_order,
            provider=provider,
            amount=locked_order.total,
            currency=SiteSetting.get_solo().default_currency or "USD",
            status=PaymentAttempt.Status.PENDING,
            is_test=False,
            external_reference=bank_transaction_reference,
            metadata={
                "source": "manual_bank_transfer",
                "internal_note": internal_note.strip(),
                "confirmed_by_user_id": actor.pk,
            },
            created_by=actor,
        )
        PaymentService.record_attempt_created(attempt=attempt, actor=actor)
        completed_attempt = PaymentService.complete_success(
            attempt=attempt,
            actor=actor,
            external_reference=bank_transaction_reference,
            event_type=PaymentStatusEvent.EventType.MANUAL_CONFIRMATION,
            reason="Bank statement matched to the invoice reference and amount.",
        )
        security_logger.warning(
            "Bank transfer confirmed for order_id=%s payment_id=%s actor_id=%s",
            locked_order.pk,
            completed_attempt.pk,
            actor.pk,
        )
        return completed_attempt

    @staticmethod
    @transaction.atomic
    def reject_bank_transfer(
        *,
        order,
        actor,
        reason,
        bank_transaction_reference="",
    ):
        """Record a rejected transfer without marking the invoice paid."""
        if not actor or not actor.is_staff or not (
            actor.is_superuser or actor.has_perm("users.confirm_bank_payments")
        ):
            raise ValidationError({"detail": "Finance payment confirmation access is required."})

        locked_order = (
            Order.objects.select_for_update()
            .select_related("quote_request")
            .get(pk=order.pk)
        )
        if not locked_order.quote_request_id:
            raise ValidationError({"order": "Manual bank review is available for quote invoices only."})
        quote_request = locked_order.quote_request
        if quote_request.status not in {
            quote_request.Status.INVOICE_SENT,
            quote_request.Status.AWAITING_PAYMENT,
            quote_request.Status.PAYMENT_REJECTED,
        } or not quote_request.invoice_number:
            raise ValidationError({"order": "This quote does not have an invoice awaiting payment."})
        if quote_request.quoted_total is None or quote_request.quoted_total != locked_order.total:
            raise ValidationError({"order": "The invoice amount does not match the order total."})
        if locked_order.status != Order.Status.PENDING:
            raise ValidationError({"order": "Only orders awaiting payment can be rejected."})
        if PaymentAttempt.objects.filter(
            order=locked_order,
            status=PaymentAttempt.Status.SUCCEEDED,
        ).exists():
            raise ValidationError({"order": "This order is already paid."})

        provider = PaymentProvider.objects.select_for_update().filter(
            code=PaymentProvider.Code.BANK_TRANSFER,
            is_enabled=True,
        ).first()
        if not provider:
            raise ValidationError({"provider": "Enable the Bank transfer provider before reviewing payment."})

        normalized_reference = bank_transaction_reference.strip().upper()
        attempt = PaymentAttempt.objects.create(
            order=locked_order,
            provider=provider,
            amount=locked_order.total,
            currency=SiteSetting.get_solo().default_currency or "USD",
            status=PaymentAttempt.Status.PENDING,
            is_test=False,
            external_reference=normalized_reference,
            metadata={
                "source": "manual_bank_transfer",
                "rejected_by_user_id": actor.pk,
            },
            created_by=actor,
        )
        PaymentService.record_attempt_created(attempt=attempt, actor=actor)
        rejected = PaymentService.mark_pending_terminal(
            attempt=attempt,
            terminal_status=PaymentAttempt.Status.FAILED,
            reason=reason.strip(),
            external_reference=normalized_reference,
            actor=actor,
            event_type=PaymentStatusEvent.EventType.MANUAL_REJECTION,
        )
        from quotes.services import QuoteService

        QuoteService.mark_payment_rejected(
            quote_request=locked_order.quote_request,
            reason=reason,
        )
        security_logger.warning(
            "Bank transfer rejected for order_id=%s payment_id=%s actor_id=%s",
            locked_order.pk,
            rejected.pk,
            actor.pk,
        )
        return rejected

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

        locked_order = Order.objects.select_for_update().select_related("organization").get(pk=order.pk)
        if not PaymentService.can_pay_order(user=user, order=locked_order):
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
        if (
            provider.code == PaymentProvider.Code.BANK_TRANSFER
            or not provider.is_customer_available
            or not provider_is_available(provider)
        ):
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
        PaymentService.record_attempt_created(attempt=attempt, actor=user)
        PaymentService.attach_provider_checkout(attempt=attempt)
        return attempt, True

    @staticmethod
    @transaction.atomic
    def start_license_renewal_checkout(*, user, license_number, organization_id, provider, idempotency_key, billing):
        from licensing.services import LicenseRenewalOrderService

        existing = (
            PaymentAttempt.objects.select_for_update()
            .select_related("renewal_license__organization", "provider", "created_by")
            .filter(idempotency_key=idempotency_key)
            .first()
        )
        if existing:
            if (
                existing.created_by_id != user.id
                or not existing.renewal_license_id
                or existing.renewal_license.license_number != license_number
                or existing.provider_id != provider.id
            ):
                raise ValidationError({"idempotency_key": "This key is already in use."})
            return existing, False

        renewal_license, product = LicenseRenewalOrderService.resolve(
            user=user,
            license_number=license_number,
            organization_id=organization_id,
            lock=True,
        )
        if (
            provider.code == PaymentProvider.Code.BANK_TRANSFER
            or not provider.is_customer_available
            or not provider_is_available(provider)
        ):
            raise ValidationError({"provider": "This payment provider is unavailable."})

        PaymentService.close_pending_renewal_attempts(
            renewal_license=renewal_license,
            reason="Replaced by a newer renewal checkout session.",
        )
        site_settings = SiteSetting.get_solo()
        attempt = PaymentAttempt.objects.create(
            renewal_license=renewal_license,
            provider=provider,
            amount=product.price_for_quantity(1),
            currency=site_settings.default_currency or "USD",
            status=PaymentAttempt.Status.PENDING,
            is_test=provider.test_mode,
            idempotency_key=idempotency_key,
            expires_at=timezone.now() + timedelta(minutes=settings.PAYMENT_SESSION_TTL_MINUTES),
            metadata={
                "source": "license_renewal",
                "billing": billing,
                "renewal_product_id": product.pk,
                "renewal_expires_on": renewal_license.expires_on.isoformat() if renewal_license.expires_on else None,
            },
            created_by=user,
        )
        PaymentService.record_attempt_created(attempt=attempt, actor=user)
        PaymentService.attach_provider_checkout(attempt=attempt)
        return attempt, True

    @staticmethod
    @transaction.atomic
    def create_admin_simulation(*, user, order, provider, outcome):
        if not (settings.DEBUG and settings.PAYMENTS_DEVELOPMENT_SIMULATOR):
            raise ValidationError({"payment": "Payment simulation is unavailable."})
        if not user or not user.is_staff or not (
            user.is_superuser or user.has_perm("users.run_payment_simulations")
        ):
            raise ValidationError({"payment": "Payment simulation access is required."})
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
        PaymentService.record_attempt_created(attempt=attempt, actor=user)
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
        locked = PaymentAttempt.objects.select_for_update().select_related(
            "order__quote_request"
        ).get(pk=attempt.pk)
        if (
            locked.status == PaymentAttempt.Status.PENDING
            and locked.expires_at
            and locked.expires_at <= timezone.now()
        ):
            previous_status = locked.status
            locked.status = PaymentAttempt.Status.EXPIRED
            locked.failure_message = "The checkout session expired."
            locked.save(update_fields=["status", "failure_message", "updated_at"])
            PaymentService._record_status_event(
                attempt=locked,
                event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
                previous_status=previous_status,
                reason=locked.failure_message,
            )
        return locked

    @staticmethod
    @transaction.atomic
    def expire_pending_attempts(*, now=None):
        now = now or timezone.now()
        attempts = PaymentAttempt.objects.select_for_update().select_related(
            "order__quote_request"
        ).filter(
            status=PaymentAttempt.Status.PENDING,
            expires_at__isnull=False,
            expires_at__lte=now,
        )
        count = 0
        for attempt in attempts:
            previous_status = attempt.status
            attempt.status = PaymentAttempt.Status.EXPIRED
            attempt.failure_message = "The checkout session expired."
            attempt.save(update_fields=["status", "failure_message", "updated_at"])
            PaymentService._record_status_event(
                attempt=attempt,
                event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
                previous_status=previous_status,
                reason=attempt.failure_message,
            )
            count += 1
        return count

    @staticmethod
    @transaction.atomic
    def mark_failed(*, attempt, reason, external_reference=""):
        return PaymentService.mark_pending_terminal(
            attempt=attempt,
            terminal_status=PaymentAttempt.Status.FAILED,
            reason=reason,
            external_reference=external_reference,
        )

    @staticmethod
    @transaction.atomic
    def mark_pending_terminal(
        *,
        attempt,
        terminal_status,
        reason,
        external_reference="",
        actor=None,
        event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
    ):
        if terminal_status not in {
            PaymentAttempt.Status.FAILED,
            PaymentAttempt.Status.CANCELLED,
            PaymentAttempt.Status.EXPIRED,
        }:
            raise ValidationError({"payment": "Unsupported terminal payment status."})
        locked = PaymentAttempt.objects.select_for_update().select_related(
            "order__quote_request"
        ).get(pk=attempt.pk)
        if locked.status != PaymentAttempt.Status.PENDING:
            return locked
        previous_status = locked.status
        locked.status = terminal_status
        locked.failure_message = reason[:500]
        if external_reference:
            locked.external_reference = external_reference[:255]
        locked.save(
            update_fields=["status", "failure_message", "external_reference", "updated_at"]
        )
        PaymentService._record_status_event(
            attempt=locked,
            event_type=event_type,
            previous_status=previous_status,
            actor=actor,
            reason=reason,
        )
        return locked

    @staticmethod
    @transaction.atomic
    def complete_success(
        *,
        attempt,
        actor,
        external_reference,
        event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
        reason="Payment verified.",
    ):
        from licensing.services import PaymentSuccessProvisioningService

        locked = (
            PaymentAttempt.objects.select_for_update()
            .select_related("order", "renewal_license__organization", "provider", "created_by")
            .get(pk=attempt.pk)
        )
        if locked.status == PaymentAttempt.Status.SUCCEEDED:
            if locked.renewal_license_id and not locked.order_id:
                PaymentService._create_renewal_order(attempt=locked)
            PaymentSuccessProvisioningService.provision(
                payment_attempt=locked,
                actor=actor,
            )
            locked_order = Order.objects.select_for_update().get(pk=locked.order_id)
            InventoryReservationService.reserve_for_order(order=locked_order)
            target_status = OrderService.status_after_successful_payment(
                order=locked_order
            )
            if locked_order.status in {
                Order.Status.PENDING,
                Order.Status.PROCESSING,
                Order.Status.SCHEDULED,
            } and locked_order.status != target_status:
                OrderService.update_status(
                    order=locked_order,
                    new_status=target_status,
                    exclude_pending_payment_attempt_id=locked.pk,
                )
            locked.refresh_from_db()
            return locked
        if locked.status != PaymentAttempt.Status.PENDING:
            return locked

        if locked.renewal_license_id and not locked.order_id:
            return PaymentService._complete_renewal_success(
                attempt=locked,
                actor=actor,
                external_reference=external_reference,
            )

        locked_order = Order.objects.select_for_update().get(pk=locked.order_id)
        another_success = PaymentAttempt.objects.filter(
            order=locked_order,
            status=PaymentAttempt.Status.SUCCEEDED,
        ).exclude(pk=locked.pk).exists()
        if another_success or locked_order.status != Order.Status.PENDING:
            previous_status = locked.status
            locked.status = PaymentAttempt.Status.CANCELLED
            locked.failure_message = (
                "The order was already paid or is no longer awaiting payment."
            )
            locked.save(update_fields=["status", "failure_message", "updated_at"])
            PaymentService._record_status_event(
                attempt=locked,
                event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
                previous_status=previous_status,
                actor=actor,
                reason=locked.failure_message,
            )
            return locked

        previous_status = locked.status
        locked.status = PaymentAttempt.Status.SUCCEEDED
        locked.failure_message = ""
        locked.external_reference = external_reference
        locked.paid_at = timezone.now()
        try:
            with transaction.atomic():
                locked.save(
                    update_fields=[
                        "status",
                        "failure_message",
                        "external_reference",
                        "paid_at",
                        "updated_at",
                    ]
                )
        except IntegrityError as exc:
            raise ValidationError({
                "external_reference": "This payment reference has already been confirmed."
            }) from exc
        PaymentService._record_status_event(
            attempt=locked,
            event_type=event_type,
            previous_status=previous_status,
            actor=actor,
            reason=reason,
        )
        InventoryReservationService.reserve_for_order(order=locked_order)
        PaymentSuccessProvisioningService.provision(
            payment_attempt=locked,
            actor=actor,
        )
        next_status = OrderService.status_after_successful_payment(order=locked_order)
        OrderService.update_status(
            order=locked_order,
            new_status=next_status,
            exclude_pending_payment_attempt_id=locked.pk,
        )
        PaymentService.close_pending_attempts(
            order=locked_order,
            exclude_attempt_id=locked.pk,
            reason="Closed after another payment succeeded.",
        )
        locked.refresh_from_db()
        return locked

    @staticmethod
    @transaction.atomic
    def mark_refunded(*, attempt, reason="Refund approved."):
        """Release an unfulfilled physical reservation after a recorded refund.

        Live-provider refund callbacks will call this method once the provider
        integration is added. It is deliberately not exposed as a client action.
        """
        locked = PaymentAttempt.objects.select_for_update().select_related("order").get(pk=attempt.pk)
        if locked.status == PaymentAttempt.Status.REFUNDED:
            return locked
        if locked.status != PaymentAttempt.Status.SUCCEEDED:
            raise ValidationError({"payment": "Only successful payments can be refunded."})
        from licensing.services import PaymentSuccessProvisioningService

        PaymentSuccessProvisioningService.reverse(
            payment_attempt=locked,
            reason=reason,
        )
        previous_status = locked.status
        locked.status = PaymentAttempt.Status.REFUNDED
        locked.failure_message = reason
        locked.save(update_fields=["status", "failure_message", "updated_at"])
        PaymentService._record_status_event(
            attempt=locked,
            event_type=PaymentStatusEvent.EventType.REFUND,
            previous_status=previous_status,
            reason=reason,
        )
        if locked.order_id and locked.order.status in {
            Order.Status.PENDING,
            Order.Status.BACKORDERED,
            Order.Status.SCHEDULED,
            Order.Status.PROCESSING,
        }:
            InventoryReservationService.release_for_order(order=locked.order, reason=reason)
            if locked.order.shipments.exists():
                # Shipped units have already left on-hand inventory. Prevent the
                # legacy whole-order cancellation path from restoring them.
                locked.order.stock_deducted = False
                locked.order.save(update_fields=["stock_deducted", "updated_at"])
            OrderService.update_status(
                order=locked.order,
                new_status=Order.Status.CANCELLED,
                allow_paid_cancellation=True,
            )
        return locked

    @staticmethod
    def _create_renewal_order(*, attempt):
        from orders.models import OrderItem
        from products.models import Product

        renewal_license = attempt.renewal_license
        billing = (attempt.metadata or {}).get("billing", {})
        product = Product.objects.select_for_update().get(
            pk=(attempt.metadata or {}).get("renewal_product_id") or renewal_license.license_product_id
        )
        order = Order.objects.create(
            user=attempt.created_by,
            organization=renewal_license.organization,
            renewal_license=renewal_license,
            source=Order.Source.DIRECT,
            customer_first_name=billing.get("first_name", ""),
            customer_last_name=billing.get("last_name", ""),
            customer_email=billing.get("email", renewal_license.organization.billing_email),
            customer_phone=billing.get("phone", ""),
            company_name=billing.get("company", renewal_license.organization.name),
            shipping_address=billing.get("address", ""),
            shipping_city=billing.get("city", ""),
            shipping_state=billing.get("state", ""),
            shipping_postal_code=billing.get("postal_code", ""),
            shipping_country=billing.get("country", ""),
            subtotal=attempt.amount,
            total=attempt.amount,
            notes=f"Renewal for license {renewal_license.license_number}.",
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            sku=product.sku,
            unit_price=attempt.amount,
            quantity=1,
            line_total=attempt.amount,
        )
        attempt.order = order
        attempt.save(update_fields=["order", "updated_at"])
        return order

    @staticmethod
    def _complete_renewal_success(*, attempt, actor, external_reference):
        from licensing.services import PaymentSuccessProvisioningService

        renewal_cycle = (attempt.metadata or {}).get("renewal_expires_on")
        another_success = PaymentAttempt.objects.filter(
            renewal_license=attempt.renewal_license,
            status=PaymentAttempt.Status.SUCCEEDED,
            metadata__renewal_expires_on=renewal_cycle,
        ).exists()
        if another_success:
            previous_status = attempt.status
            attempt.status = PaymentAttempt.Status.CANCELLED
            attempt.failure_message = "This license renewal was already paid."
            attempt.save(update_fields=["status", "failure_message", "updated_at"])
            PaymentService._record_status_event(
                attempt=attempt,
                event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
                previous_status=previous_status,
                actor=actor,
                reason=attempt.failure_message,
            )
            return attempt

        order = PaymentService._create_renewal_order(attempt=attempt)
        previous_status = attempt.status
        attempt.status = PaymentAttempt.Status.SUCCEEDED
        attempt.failure_message = ""
        attempt.external_reference = external_reference
        attempt.paid_at = timezone.now()
        attempt.save(update_fields=["status", "failure_message", "external_reference", "paid_at", "updated_at"])
        PaymentService._record_status_event(
            attempt=attempt,
            event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
            previous_status=previous_status,
            actor=actor,
            reason="License renewal payment verified.",
        )
        PaymentSuccessProvisioningService.provision(payment_attempt=attempt, actor=actor)
        OrderService.update_status(
            order=order,
            new_status=OrderService.status_after_successful_payment(order=order),
            exclude_pending_payment_attempt_id=attempt.pk,
        )
        PaymentService.close_pending_attempts(
            order=order,
            exclude_attempt_id=attempt.pk,
            reason="Closed after successful renewal payment.",
        )
        PaymentService.close_pending_renewal_attempts(
            renewal_license=attempt.renewal_license,
            exclude_attempt_id=attempt.pk,
            reason="Closed after successful renewal payment.",
        )
        attempt.refresh_from_db()
        return attempt

    @staticmethod
    @transaction.atomic
    def simulate_checkout(*, attempt, user, outcome):
        locked = (
            PaymentAttempt.objects.select_for_update()
            .select_related("order", "renewal_license__organization", "provider", "created_by")
            .get(pk=attempt.pk)
        )
        if not PaymentService.can_pay_attempt(user=user, attempt=locked) and locked.created_by_id != user.id:
            raise ValidationError({"session": "This payment session is not available."})
        if locked.status == PaymentAttempt.Status.SUCCEEDED:
            return PaymentService.complete_success(
                attempt=locked,
                actor=user,
                external_reference=locked.external_reference,
            )
        if locked.status != PaymentAttempt.Status.PENDING:
            return locked
        if locked.expires_at and locked.expires_at <= timezone.now():
            previous_status = locked.status
            locked.status = PaymentAttempt.Status.EXPIRED
            locked.failure_message = "The development checkout session expired."
            locked.save(update_fields=["status", "failure_message", "updated_at"])
            PaymentService._record_status_event(
                attempt=locked,
                event_type=PaymentStatusEvent.EventType.STATUS_CHANGE,
                previous_status=previous_status,
                actor=user,
                reason=locked.failure_message,
            )
            return locked

        if outcome == PaymentAttempt.Status.FAILED:
            return PaymentService.mark_failed(
                attempt=locked,
                reason="Simulated provider decline.",
                external_reference=f"dev_failed_{locked.pk}",
            )

        return PaymentService.complete_success(
            attempt=locked,
            actor=user,
            external_reference=f"dev_paid_{locked.pk}",
        )


class PaymentProviderCallbackService:
    """Processes a callback only after an adapter has verified its signature."""

    @staticmethod
    @transaction.atomic
    def process(*, provider, callback, payload: bytes):
        digest = hashlib.sha256(payload).hexdigest()
        event, created = PaymentProviderEvent.objects.select_for_update().get_or_create(
            provider=provider,
            event_id=callback.event_id,
            defaults={"payload_sha256": digest},
        )
        if not created:
            return event, False

        attempt = PaymentAttempt.objects.select_for_update().filter(
            provider=provider,
            reference=callback.payment_reference,
        ).first()
        if not attempt:
            event.status = PaymentProviderEvent.Status.IGNORED
            event.error_message = "Payment reference was not found."
            event.processed_at = timezone.now()
            event.save(update_fields=["status", "error_message", "processed_at", "updated_at"])
            return event, True

        event.payment_attempt = attempt
        event.provider_transaction_id = callback.transaction_id[:255]
        event.outcome = callback.outcome
        try:
            received_amount = Decimal(callback.amount)
        except (InvalidOperation, TypeError):
            received_amount = None
        if received_amount != attempt.amount or callback.currency != attempt.currency:
            event.status = PaymentProviderEvent.Status.FAILED
            event.error_message = "Provider callback amount or currency did not match the payment attempt."
            event.processed_at = timezone.now()
            event.save(update_fields=[
                "payment_attempt", "provider_transaction_id", "outcome", "status",
                "error_message", "processed_at", "updated_at",
            ])
            return event, True

        if callback.outcome == PaymentAttempt.Status.SUCCEEDED:
            PaymentService.complete_success(
                attempt=attempt,
                actor=None,
                external_reference=callback.transaction_id,
            )
        elif callback.outcome == PaymentAttempt.Status.REFUNDED:
            PaymentService.mark_refunded(
                attempt=attempt,
                reason="Verified provider refund.",
            )
        elif callback.outcome in {
            PaymentAttempt.Status.FAILED,
            PaymentAttempt.Status.CANCELLED,
            PaymentAttempt.Status.EXPIRED,
        }:
            PaymentService.mark_pending_terminal(
                attempt=attempt,
                terminal_status=callback.outcome,
                reason=f"Verified provider payment {callback.outcome}.",
                external_reference=callback.transaction_id,
            )
        else:
            event.status = PaymentProviderEvent.Status.IGNORED
            event.error_message = "Provider callback outcome is not supported."
            event.processed_at = timezone.now()
            event.save(update_fields=[
                "payment_attempt", "provider_transaction_id", "outcome", "status",
                "error_message", "processed_at", "updated_at",
            ])
            return event, True

        event.status = PaymentProviderEvent.Status.PROCESSED
        event.processed_at = timezone.now()
        event.save(update_fields=[
            "payment_attempt", "provider_transaction_id", "outcome", "status",
            "processed_at", "updated_at",
        ])
        return event, True
