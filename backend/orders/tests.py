from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from licensing.models import License, LicenseEvent, Organization, OrganizationMembership
from licensing.services import OrganizationService
from orders.models import InventoryReservation, Order, OrderItem
from orders.services import OrderService
from payments.models import PaymentAttempt, PaymentProvider
from payments.services import PaymentService
from products.models import Category, Product


class AdminManualOrderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="manual-admin",
            email="manual-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.client_user = User.objects.create_user(
            username="manual-client",
            email="manual-client@example.com",
            password="StrongPass123!",
            first_name="Manual",
            last_name="Client",
        )
        self.organization = OrganizationService.create(
            name="Manual Order Corp",
            owner=self.client_user,
        )
        category = Category.objects.create(name="Manual products")
        self.license_product = Product.objects.create(
            category=category,
            name="Manual Business License",
            sku="MAN-LIC-200",
            price="1000.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=200,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )
        self.physical_product = Product.objects.create(
            category=category,
            name="Manual Radio",
            sku="MAN-RADIO-1",
            price="250.00",
            inventory_quantity=10,
            status=Product.Status.PUBLISHED,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def payload(self, *, product, payment_state, reference=""):
        return {
            "customer_mode": "existing",
            "customer_id": self.client_user.pk,
            "organization_mode": "existing",
            "organization_id": self.organization.pk,
            "payment_state": payment_state,
            "payment_reference": reference,
            "items": [{"product": product.pk, "quantity": 1}],
        }

    def test_draft_has_no_payment_or_provisioning_and_is_hidden_from_client(self):
        response = self.api.post(
            "/api/v1/orders/manual/",
            self.payload(product=self.license_product, payment_state="draft"),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.status, Order.Status.DRAFT)
        self.assertFalse(PaymentAttempt.objects.filter(order=order).exists())
        self.assertFalse(License.objects.filter(source_order_item__order=order).exists())

        self.api.force_authenticate(self.client_user)
        client_orders = self.api.get("/api/v1/orders/")
        self.assertNotIn(order.order_number, [item["order_number"] for item in client_orders.data["results"]])

    def test_waiting_payment_stays_pending_without_provisioning(self):
        response = self.api.post(
            "/api/v1/orders/manual/",
            self.payload(product=self.license_product, payment_state="waiting_payment"),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(PaymentAttempt.objects.filter(order=order).exists())
        self.assertFalse(License.objects.filter(source_order_item__order=order).exists())

    def test_paid_digital_order_completes_and_provisions(self):
        response = self.api.post(
            "/api/v1/orders/manual/",
            self.payload(
                product=self.license_product,
                payment_state="paid",
                reference="BANK-VERIFIED-1001",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(order.user, self.client_user)
        self.assertEqual(order.created_by, self.staff)
        self.assertEqual(order.source, Order.Source.ADMIN)
        self.assertTrue(PaymentAttempt.objects.filter(order=order, status="succeeded").exists())
        self.assertTrue(License.objects.filter(source_order_item__order=order).exists())

    def test_admin_organization_choices_are_filtered_to_selected_client(self):
        other_user = get_user_model().objects.create_user(
            username="other-manual-client",
            email="other-manual-client@example.com",
            password="StrongPass123!",
        )
        other_organization = OrganizationService.create(
            name="Other Manual Corp",
            owner=other_user,
        )

        response = self.api.get(
            f"/api/v1/admin/licensing/organizations/?customer_id={self.client_user.pk}"
        )

        self.assertEqual(response.status_code, 200)
        organization_ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.organization.pk, organization_ids)
        self.assertNotIn(other_organization.pk, organization_ids)

    def test_paid_physical_order_is_scheduled_without_early_stock_deduction(self):
        response = self.api.post(
            "/api/v1/orders/manual/",
            self.payload(
                product=self.physical_product,
                payment_state="paid",
                reference="BANK-VERIFIED-1002",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.status, Order.Status.SCHEDULED)
        self.assertFalse(order.stock_deducted)
        reservation = InventoryReservation.objects.get(order_item__order=order)
        self.assertEqual(reservation.status, InventoryReservation.Status.RESERVED)
        self.assertEqual(reservation.quantity, 1)


class InventoryReservationLifecycleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(
            username="reservation-customer",
            email="reservation-customer@example.com",
            password="StrongPass123!",
        )
        category = Category.objects.create(name="Reservation products")
        self.product = Product.objects.create(
            category=category,
            name="Reservation radio",
            sku="RESERVE-RADIO",
            price="250.00",
            inventory_quantity=2,
            status=Product.Status.PUBLISHED,
        )
        self.provider, _ = PaymentProvider.objects.get_or_create(
            code=PaymentProvider.Code.STRIPE,
            defaults={"display_name": "Stripe", "is_enabled": True, "test_mode": True},
        )

    def create_order(self, *, quantity=1):
        order = Order.objects.create(
            user=self.customer,
            source=Order.Source.DIRECT,
            customer_first_name="Reservation",
            customer_last_name="Customer",
            customer_email=self.customer.email,
            shipping_address="1 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal=str(250 * quantity),
            total=str(250 * quantity),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price="250.00",
            quantity=quantity,
            line_total=str(250 * quantity),
        )
        return order

    def pay(self, order):
        attempt = PaymentAttempt.objects.create(
            order=order,
            provider=self.provider,
            amount=order.total,
            currency="USD",
            is_test=True,
            status=PaymentAttempt.Status.PENDING,
            created_by=self.customer,
        )
        return PaymentService.complete_success(
            attempt=attempt,
            actor=self.customer,
            external_reference=f"TEST-{attempt.pk}",
        )

    def test_paid_physical_order_reserves_stock_then_consumes_it_during_processing(self):
        order = self.create_order(quantity=2)
        self.pay(order)

        order.refresh_from_db()
        self.product.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item__order=order)
        self.assertEqual(order.status, Order.Status.SCHEDULED)
        self.assertFalse(order.stock_deducted)
        self.assertEqual(self.product.inventory_quantity, 2)
        self.assertEqual(reservation.status, InventoryReservation.Status.RESERVED)

        OrderService.update_status(order=order, new_status=Order.Status.PROCESSING)
        order.refresh_from_db()
        self.product.refresh_from_db()
        reservation.refresh_from_db()
        self.assertTrue(order.stock_deducted)
        self.assertEqual(self.product.inventory_quantity, 0)
        self.assertEqual(reservation.status, InventoryReservation.Status.CONSUMED)
        self.assertIsNotNone(reservation.consumed_at)

        OrderService.update_status(order=order, new_status=Order.Status.COMPLETED)
        self.product.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 0)
        self.assertEqual(reservation.status, InventoryReservation.Status.CONSUMED)

    def test_active_reservation_is_subtracted_from_public_catalog_stock(self):
        order = self.create_order(quantity=1)
        self.pay(order)

        response = APIClient().get("/api/v1/products/catalog/reservation-radio/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["inventory_quantity"], 1)
        self.assertEqual(response.data["on_hand_inventory_quantity"], 2)
        self.assertEqual(response.data["reserved_inventory_quantity"], 1)

    def test_competing_paid_orders_cannot_over_reserve_stock(self):
        first = self.create_order(quantity=2)
        second = self.create_order(quantity=1)
        self.pay(first)

        with self.assertRaises(ValidationError):
            self.pay(second)

        second.refresh_from_db()
        self.assertEqual(second.status, Order.Status.PENDING)
        self.assertFalse(InventoryReservation.objects.filter(order_item__order=second).exists())

    def test_approved_cancellation_releases_an_unfulfilled_reservation(self):
        order = self.create_order(quantity=1)
        self.pay(order)

        OrderService.update_status(
            order=order,
            new_status=Order.Status.CANCELLED,
            allow_paid_cancellation=True,
        )

        reservation = InventoryReservation.objects.get(order_item__order=order)
        self.assertEqual(reservation.status, InventoryReservation.Status.RELEASED)
        self.assertEqual(reservation.release_reason, "Order cancelled before fulfillment.")

    def test_failed_payment_creates_no_reservation(self):
        order = self.create_order(quantity=1)
        attempt = PaymentAttempt.objects.create(
            order=order,
            provider=self.provider,
            amount=order.total,
            currency="USD",
            is_test=True,
            status=PaymentAttempt.Status.PENDING,
            created_by=self.customer,
        )

        attempt.status = PaymentAttempt.Status.FAILED
        attempt.save(update_fields=["status", "updated_at"])

        self.assertFalse(InventoryReservation.objects.filter(order_item__order=order).exists())

    def test_refund_releases_an_unfulfilled_reservation_and_cancels_the_order(self):
        order = self.create_order(quantity=1)
        attempt = self.pay(order)

        PaymentService.mark_refunded(attempt=attempt, reason="Provider refund confirmed.")

        order.refresh_from_db()
        self.product.refresh_from_db()
        reservation = InventoryReservation.objects.get(order_item__order=order)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.inventory_quantity, 2)
        self.assertEqual(reservation.status, InventoryReservation.Status.RELEASED)
        self.assertEqual(reservation.release_reason, "Provider refund confirmed.")


class AdminOrganizationCreationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="organization-admin",
            email="organization-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def test_draft_organization_has_no_owner(self):
        response = self.api.post(
            "/api/v1/admin/licensing/organizations/",
            {"name": "Future Corp", "owner_mode": "draft"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        organization = Organization.objects.get(pk=response.data["id"])
        self.assertEqual(organization.status, Organization.Status.DRAFT)
        self.assertFalse(organization.memberships.exists())

    def test_owner_invitation_activates_draft_when_accepted(self):
        response = self.api.post(
            "/api/v1/admin/licensing/organizations/",
            {"name": "Invited Corp", "owner_mode": "invite", "owner_email": "owner-invite@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        organization = Organization.objects.get(pk=response.data["id"])
        self.assertEqual(organization.status, Organization.Status.DRAFT)
        token = response.data["invitation"]["accept_url"].split("token=", 1)[1]
        owner = get_user_model().objects.create_user(
            username="owner-invite",
            email="owner-invite@example.com",
            password="StrongPass123!",
        )
        self.api.force_authenticate(owner)
        accepted = self.api.post(
            "/api/v1/licensing/organization/invitations/accept/",
            {"token": token},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200)
        organization.refresh_from_db()
        self.assertEqual(organization.status, Organization.Status.ACTIVE)
        self.assertEqual(organization.memberships.get(role="owner").user, owner)

    def test_staff_can_assign_the_initial_owner_from_a_draft_license_manager(self):
        manager = get_user_model().objects.create_user(
            username="draft-manager",
            email="draft-manager@example.com",
            password="StrongPass123!",
        )
        organization = OrganizationService.create_draft(
            name="Owner Assignment Corp",
            created_by=self.staff,
        )
        membership = OrganizationMembership.objects.create(
            organization=organization,
            user=manager,
            role=OrganizationMembership.Role.LICENSE_MANAGER,
        )

        response = self.api.post(
            f"/api/v1/admin/licensing/organizations/{organization.pk}/users/ownership-transfer/",
            {"membership_id": membership.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        organization.refresh_from_db()
        membership.refresh_from_db()
        self.assertEqual(organization.status, Organization.Status.ACTIVE)
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)
        event = LicenseEvent.objects.get(organization=organization)
        self.assertTrue(event.metadata["initial_owner_assigned"])
        self.assertIsNone(event.metadata["previous_owner_id"])
