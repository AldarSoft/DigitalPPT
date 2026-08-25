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
        if not provider_is_available(provider):
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
        locked.save(
            update_fields=[
                "status",
                "failure_message",
                "external_reference",
                "paid_at",
                "updated_at",
            ]
        )
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
            locked.status = PaymentAttempt.Status.FAILED
            locked.failure_message = "Simulated provider decline."
            locked.external_reference = f"dev_failed_{locked.pk}"
            locked.save(update_fields=["status", "failure_message", "external_reference", "updated_at"])
            return locked

        return PaymentService.complete_success(
            attempt=locked,
            actor=user,
            external_reference=f"dev_paid_{locked.pk}",
        )
