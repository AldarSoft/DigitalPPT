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
from payments.models import PaymentAttempt, PaymentProvider, PaymentProviderEvent
from payments.providers import get_provider_adapter, provider_is_available


security_logger = logging.getLogger("security.payments")


class PaymentService:
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
        if user.is_staff or order.user_id == user.id:
            return True
        if not order.organization_id:
            return False
        from licensing.permissions import OrganizationAccessPolicy

        return OrganizationAccessPolicy.can_manage_billing(
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
    def confirm_bank_transfer(*, order, actor, bank_transaction_reference, internal_note=""):
        """Record a staff-verified transfer and run the standard success workflow."""
        if not actor or not actor.is_staff:
            raise ValidationError({"detail": "Administrator access is required."})

        locked_order = (
            Order.objects.select_for_update()
            .select_related("quote_request")
            .get(pk=order.pk)
        )
        if not locked_order.quote_request_id:
            raise ValidationError({"order": "Manual bank confirmation is available for quote invoices only."})
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
        return PaymentService.complete_success(
            attempt=attempt,
            actor=actor,
            external_reference=bank_transaction_reference,
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

        PaymentAttempt.objects.filter(
            renewal_license=renewal_license,
            status=PaymentAttempt.Status.PENDING,
        ).update(
            status=PaymentAttempt.Status.CANCELLED,
            failure_message="Replaced by a newer renewal checkout session.",
            updated_at=timezone.now(),
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
        PaymentService.attach_provider_checkout(attempt=attempt)
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
    def expire_pending_attempts(*, now=None):
        now = now or timezone.now()
        return PaymentAttempt.objects.filter(
            status=PaymentAttempt.Status.PENDING,
            expires_at__isnull=False,
            expires_at__lte=now,
        ).update(
            status=PaymentAttempt.Status.EXPIRED,
            failure_message="The checkout session expired.",
            updated_at=now,
        )

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
    def mark_pending_terminal(*, attempt, terminal_status, reason, external_reference=""):
        if terminal_status not in {
            PaymentAttempt.Status.FAILED,
            PaymentAttempt.Status.CANCELLED,
            PaymentAttempt.Status.EXPIRED,
        }:
            raise ValidationError({"payment": "Unsupported terminal payment status."})
        locked = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status != PaymentAttempt.Status.PENDING:
            return locked
        locked.status = terminal_status
        locked.failure_message = reason[:500]
        if external_reference:
            locked.external_reference = external_reference[:255]
        locked.save(
            update_fields=["status", "failure_message", "external_reference", "updated_at"]
        )
        return locked

    @staticmethod
    @transaction.atomic
    def complete_success(*, attempt, actor, external_reference):
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
            locked.status = PaymentAttempt.Status.CANCELLED
            locked.failure_message = (
                "The order was already paid or is no longer awaiting payment."
            )
            locked.save(update_fields=["status", "failure_message", "updated_at"])
            return locked

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
        locked.status = PaymentAttempt.Status.REFUNDED
        locked.failure_message = reason
        locked.save(update_fields=["status", "failure_message", "updated_at"])
        if locked.order_id and locked.order.status in {Order.Status.PENDING, Order.Status.SCHEDULED, Order.Status.PROCESSING}:
            InventoryReservationService.release_for_order(order=locked.order, reason=reason)
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
            attempt.status = PaymentAttempt.Status.CANCELLED
            attempt.failure_message = "This license renewal was already paid."
            attempt.save(update_fields=["status", "failure_message", "updated_at"])
            return attempt

        order = PaymentService._create_renewal_order(attempt=attempt)
        attempt.status = PaymentAttempt.Status.SUCCEEDED
        attempt.failure_message = ""
        attempt.external_reference = external_reference
        attempt.paid_at = timezone.now()
        attempt.save(update_fields=["status", "failure_message", "external_reference", "paid_at", "updated_at"])
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
        PaymentAttempt.objects.filter(
            renewal_license=attempt.renewal_license,
            status=PaymentAttempt.Status.PENDING,
        ).exclude(pk=attempt.pk).update(
            status=PaymentAttempt.Status.CANCELLED,
            failure_message="Closed after successful renewal payment.",
            updated_at=timezone.now(),
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
            locked.status = PaymentAttempt.Status.EXPIRED
            locked.failure_message = "The development checkout session expired."
            locked.save(update_fields=["status", "failure_message", "updated_at"])
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
