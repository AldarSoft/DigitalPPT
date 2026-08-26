from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from orders.models import InventoryReservation, Order, OrderItem
from orders.services import OrderService
from licensing.services import OrganizationService
from licensing.models import OrganizationMembership
from payments.models import PaymentAttempt, PaymentProvider, PaymentProviderEvent
from payments.providers import VerifiedProviderCallback
from payments.services import PaymentProviderCallbackService
from products.models import Category, Product
from quotes.models import QuoteRequest


class PaymentFoundationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="payment-admin@example.com",
            email="payment-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            username="payment-customer@example.com",
            email="payment-customer@example.com",
            password="StrongPass123!",
        )
        self.order = Order.objects.create(
            user=self.customer,
            customer_first_name="Payment",
            customer_last_name="Tester",
            customer_email=self.customer.email,
            shipping_address="1 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal="680.00",
            total="680.00",
        )

    def test_payment_status_is_staff_only_and_storefront_is_disabled(self):
        anonymous = self.client.get("/api/v1/payments/status/")
        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/payments/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["storefront_enabled"], settings.PAYMENTS_STOREFRONT_ENABLED)
        self.assertFalse(response.data["live_processing_available"])
        self.assertEqual(len(response.data["providers"]), 4)
        self.assertTrue(all("integration_state" in provider for provider in response.data["providers"]))

    def test_live_callback_route_stays_hidden_without_a_registered_adapter(self):
        PaymentProvider.objects.filter(code="qpay").update(test_mode=False)

        response = self.client.post(
            "/api/v1/payments/provider-callbacks/qpay/",
            b"unverified callback",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_verified_callback_is_idempotent_and_completes_the_matching_attempt(self):
        provider = PaymentProvider.objects.get(code="stripe")
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            provider=provider,
            amount=self.order.total,
            currency="USD",
            created_by=self.customer,
        )
        callback = VerifiedProviderCallback(
            event_id="provider-event-1",
            payment_reference=attempt.reference,
            transaction_id="provider-transaction-1",
            outcome=PaymentAttempt.Status.SUCCEEDED,
            amount="680.00",
            currency="USD",
        )

        event, created = PaymentProviderCallbackService.process(
            provider=provider,
            callback=callback,
            payload=b'{"event":"paid"}',
        )
        repeated, repeated_created = PaymentProviderCallbackService.process(
            provider=provider,
            callback=callback,
            payload=b'{"event":"paid"}',
        )

        attempt.refresh_from_db()
        self.order.refresh_from_db()
        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(event.pk, repeated.pk)
        self.assertEqual(event.status, PaymentProviderEvent.Status.PROCESSED)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.SCHEDULED)

    def test_reconciliation_command_expires_stale_payment_sessions(self):
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            provider=PaymentProvider.objects.get(code="stripe"),
            amount=self.order.total,
            expires_at=timezone.now() - timedelta(minutes=1),
            created_by=self.customer,
        )

        call_command("reconcile_payments")

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.EXPIRED)

    def test_verified_callback_preserves_a_provider_cancellation_status(self):
        provider = PaymentProvider.objects.get(code="stripe")
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            provider=provider,
            amount=self.order.total,
            currency="USD",
            created_by=self.customer,
        )
        callback = VerifiedProviderCallback(
            event_id="provider-event-cancelled",
            payment_reference=attempt.reference,
            transaction_id="provider-transaction-cancelled",
            outcome=PaymentAttempt.Status.CANCELLED,
            amount="680.00",
            currency="USD",
        )

        event, _ = PaymentProviderCallbackService.process(
            provider=provider,
            callback=callback,
            payload=b'{"event":"cancelled"}',
        )

        attempt.refresh_from_db()
        self.assertEqual(event.status, PaymentProviderEvent.Status.PROCESSED)
        self.assertEqual(attempt.status, PaymentAttempt.Status.CANCELLED)

    def test_admin_successful_payment_schedules_order_and_reserves_inventory(self):
        category = Category.objects.create(name="Payment products")
        product = Product.objects.create(
            category=category,
            name="Payment radio",
            sku="PAY-RADIO",
            price="340.00",
            inventory_quantity=5,
            status=Product.Status.PUBLISHED,
        )
        OrderItem.objects.create(
            order=self.order,
            product=product,
            product_name=product.name,
            sku=product.sku,
            unit_price="340.00",
            quantity=2,
            line_total="680.00",
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/v1/payments/attempts/",
            {"order_number": self.order.order_number, "provider": "stripe", "outcome": "succeeded"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["amount"], 680)
        self.assertTrue(response.data["is_test"])
        self.assertEqual(response.data["status"], PaymentAttempt.Status.SUCCEEDED)
        self.order.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SCHEDULED)
        self.assertFalse(self.order.stock_deducted)
        self.assertEqual(product.inventory_quantity, 5)
        reservation = InventoryReservation.objects.get(order_item__order=self.order)
        self.assertEqual(reservation.status, InventoryReservation.Status.RESERVED)
        self.assertEqual(reservation.quantity, 2)

    def test_customer_cannot_list_or_simulate_payments(self):
        self.client.force_authenticate(self.customer)
        list_response = self.client.get("/api/v1/payments/attempts/")
        create_response = self.client.post(
            "/api/v1/payments/attempts/",
            {"order_number": self.order.order_number, "provider": "stripe", "outcome": "succeeded"},
            format="json",
        )
        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_disabled_provider_cannot_be_simulated(self):
        PaymentProvider.objects.filter(code="stripe").update(is_enabled=False)
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/v1/payments/attempts/",
            {"order_number": self.order.order_number, "provider": "stripe", "outcome": "succeeded"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def checkout_payload(self, *, order=None, idempotency_key=None):
        order = order or self.order
        return {
            "order_number": order.order_number,
            "provider": "stripe",
            "idempotency_key": str(idempotency_key or uuid4()),
            "billing": {
                "email": self.customer.email,
                "first_name": "Payment",
                "last_name": "Tester",
                "company": "",
                "address": "1 Main Street",
                "city": "Ulaanbaatar",
                "state": "",
                "postal_code": "14200",
                "country": "Mongolia",
            },
        }

    @override_settings(DEBUG=True, PAYMENTS_STOREFRONT_ENABLED=True, PAYMENTS_DEVELOPMENT_SIMULATOR=True)
    def test_license_manager_can_list_and_pay_an_organization_order(self):
        User = get_user_model()
        manager = User.objects.create_user(
            username="license-manager-payment@example.com",
            email="license-manager-payment@example.com",
            password="StrongPass123!",
        )
        organization = OrganizationService.create(
            name="Payment Operations",
            owner=self.customer,
            billing_email=self.customer.email,
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=manager,
            role=OrganizationMembership.Role.LICENSE_MANAGER,
        )
        self.order.organization = organization
        self.order.save(update_fields=["organization", "updated_at"])
        self.client.force_authenticate(manager)

        listed = self.client.get(f"/api/v1/orders/?organization={organization.pk}")
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        rows = listed.data["results"] if "results" in listed.data else listed.data
        self.assertEqual([row["order_number"] for row in rows], [self.order.order_number])

        payload = self.checkout_payload()
        payload["billing"]["email"] = manager.email
        created = self.client.post("/api/v1/payments/checkout-sessions/", payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        completed = self.client.post(
            f"/api/v1/payments/checkout-sessions/{created.data['session_id']}/simulate/",
            {"outcome": "succeeded"},
            format="json",
        )
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertEqual(completed.data["status"], PaymentAttempt.Status.SUCCEEDED)

    @override_settings(PAYMENTS_STOREFRONT_ENABLED=True, PAYMENTS_DEVELOPMENT_SIMULATOR=True)
    def test_license_manager_cannot_access_another_organizations_order(self):
        User = get_user_model()
        manager = User.objects.create_user(
            username="limited-license-manager@example.com",
            email="limited-license-manager@example.com",
            password="StrongPass123!",
        )
        organization = OrganizationService.create(
            name="Manager Organization",
            owner=self.customer,
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=manager,
            role=OrganizationMembership.Role.LICENSE_MANAGER,
        )
        other_owner = User.objects.create_user(
            username="unrelated-owner@example.com",
            email="unrelated-owner@example.com",
            password="StrongPass123!",
        )
        unrelated = OrganizationService.create(name="Unrelated Organization", owner=other_owner)
        self.order.organization = unrelated
        self.order.save(update_fields=["organization", "updated_at"])
        self.client.force_authenticate(manager)

        response = self.client.post(
            "/api/v1/payments/checkout-sessions/",
            self.checkout_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(DEBUG=True, PAYMENTS_STOREFRONT_ENABLED=True, PAYMENTS_DEVELOPMENT_SIMULATOR=True)
    def test_customer_can_create_idempotent_checkout_session_for_owned_order(self):
        key = uuid4()
        payload = self.checkout_payload(idempotency_key=key)
        self.client.force_authenticate(self.customer)

        created = self.client.post("/api/v1/payments/checkout-sessions/", payload, format="json")
        repeated = self.client.post("/api/v1/payments/checkout-sessions/", payload, format="json")

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(created.data["session_id"], str(key))
        self.assertEqual(created.data["status"], PaymentAttempt.Status.PENDING)
        self.assertIn("/payment?session=", created.data["checkout_url"])
        self.assertEqual(PaymentAttempt.objects.filter(idempotency_key=key).count(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    @override_settings(DEBUG=True, PAYMENTS_STOREFRONT_ENABLED=True, PAYMENTS_DEVELOPMENT_SIMULATOR=True)
    def test_new_checkout_session_cancels_the_previous_pending_session(self):
        self.client.force_authenticate(self.customer)
        first = self.client.post(
            "/api/v1/payments/checkout-sessions/",
            self.checkout_payload(),
            format="json",
        )
        second = self.client.post(
            "/api/v1/payments/checkout-sessions/",
            self.checkout_payload(),
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        first_attempt = PaymentAttempt.objects.get(idempotency_key=first.data["session_id"])
        self.assertEqual(first_attempt.status, PaymentAttempt.Status.CANCELLED)

        stale_confirmation = self.client.post(
            f"/api/v1/payments/checkout-sessions/{first.data['session_id']}/simulate/",
            {"outcome": "succeeded"},
            format="json",
        )
        successful_confirmation = self.client.post(
            f"/api/v1/payments/checkout-sessions/{second.data['session_id']}/simulate/",
            {"outcome": "succeeded"},
            format="json",
        )

        self.assertEqual(stale_confirmation.data["status"], PaymentAttempt.Status.CANCELLED)
        self.assertEqual(successful_confirmation.data["status"], PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(
            PaymentAttempt.objects.filter(
                order=self.order,
                status=PaymentAttempt.Status.SUCCEEDED,
            ).count(),
            1,
        )

    @override_settings(DEBUG=True, PAYMENTS_STOREFRONT_ENABLED=True, PAYMENTS_DEVELOPMENT_SIMULATOR=True)
    def test_expired_session_is_reconciled_when_loaded(self):
        self.client.force_authenticate(self.customer)
        created = self.client.post(
            "/api/v1/payments/checkout-sessions/",
            self.checkout_payload(),
            format="json",
        )
        PaymentAttempt.objects.filter(idempotency_key=created.data["session_id"]).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.get(
            f"/api/v1/payments/checkout-sessions/{created.data['session_id']}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], PaymentAttempt.Status.EXPIRED)

    @override_settings(PAYMENTS_STOREFRONT_ENABLED=True, PAYMENTS_DEVELOPMENT_SIMULATOR=True)
    def test_customer_cannot_create_session_for_another_users_order(self):
        User = get_user_model()
        other = User.objects.create_user(
            username="other-payment@example.com",
            email="other-payment@example.com",
            password="StrongPass123!",
        )
        other_order = Order.objects.create(
            user=other,
            customer_first_name="Other",
            customer_last_name="Customer",
            customer_email=other.email,
            shipping_address="2 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal="100.00",
            total="100.00",
        )
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            "/api/v1/payments/checkout-sessions/",
            self.checkout_payload(order=other_order),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(
        DEBUG=True,
        PAYMENTS_STOREFRONT_ENABLED=True,
        PAYMENTS_DEVELOPMENT_SIMULATOR=True,
    )
    def test_development_confirmation_marks_payment_successful_and_processes_order(self):
        self.client.force_authenticate(self.customer)
        created = self.client.post(
            "/api/v1/payments/checkout-sessions/",
            self.checkout_payload(),
            format="json",
        )

        response = self.client.post(
            f"/api/v1/payments/checkout-sessions/{created.data['session_id']}/simulate/",
            {"outcome": "succeeded"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], PaymentAttempt.Status.SUCCEEDED)
        self.assertIsNotNone(response.data["paid_at"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SCHEDULED)

    @override_settings(
        DEBUG=True,
        PAYMENTS_STOREFRONT_ENABLED=True,
        PAYMENTS_DEVELOPMENT_SIMULATOR=True,
    )
    def test_invoice_payment_schedules_quote_order(self):
        quote = QuoteRequest.objects.create(
            user=self.customer,
            requester_contact_person="Payment Tester",
            requester_email=self.customer.email,
            status=QuoteRequest.Status.QUOTED,
        )
        self.order.quote_request = quote
        self.order.source = Order.Source.QUOTE
        self.order.save(update_fields=["quote_request", "source", "updated_at"])
        self.client.force_authenticate(self.customer)
        created = self.client.post(
            "/api/v1/payments/checkout-sessions/",
            self.checkout_payload(),
            format="json",
        )

        response = self.client.post(
            f"/api/v1/payments/checkout-sessions/{created.data['session_id']}/simulate/",
            {"outcome": "succeeded"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_status"], Order.Status.SCHEDULED)
        self.order.refresh_from_db()
        quote.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SCHEDULED)
        self.assertEqual(quote.status, QuoteRequest.Status.APPROVED)

        OrderService.update_status(order=self.order, new_status=Order.Status.COMPLETED)
        quote.refresh_from_db()
        self.assertEqual(quote.status, QuoteRequest.Status.APPROVED)

    def test_terminal_order_closes_pending_payment_attempts(self):
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            provider=PaymentProvider.objects.get(code="stripe"),
            amount=self.order.total,
            created_by=self.customer,
        )

        OrderService.update_status(order=self.order, new_status=Order.Status.COMPLETED)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.CANCELLED)

    @override_settings(
        DEBUG=False,
        PAYMENTS_STOREFRONT_ENABLED=True,
        PAYMENTS_DEVELOPMENT_SIMULATOR=False,
    )
    def test_development_confirmation_is_unavailable_in_production_mode(self):
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            provider=PaymentProvider.objects.get(code="stripe"),
            amount=self.order.total,
            created_by=self.customer,
        )
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            f"/api/v1/payments/checkout-sessions/{attempt.idempotency_key}/simulate/",
            {"outcome": "succeeded"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(PAYMENTS_STOREFRONT_ENABLED=False)
    def test_checkout_session_is_hidden_when_storefront_payments_are_disabled(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            "/api/v1/payments/checkout-sessions/",
            self.checkout_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(
        DEBUG=True,
        PAYMENTS_STOREFRONT_ENABLED=True,
        PAYMENTS_DEVELOPMENT_SIMULATOR=True,
    )
    def test_storefront_status_exposes_test_providers_in_development(self):
        response = self.client.get("/api/v1/payments/storefront-status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["storefront_enabled"])
        self.assertTrue(response.data["development_simulator"])
        self.assertEqual(len(response.data["providers"]), 4)

    @override_settings(
        DEBUG=False,
        PAYMENTS_STOREFRONT_ENABLED=True,
        PAYMENTS_DEVELOPMENT_SIMULATOR=False,
    )
    def test_storefront_stays_hidden_without_a_live_provider_adapter(self):
        response = self.client.get("/api/v1/payments/storefront-status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["storefront_enabled"])
        self.assertEqual(response.data["providers"], [])
