from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from licensing.models import License, Organization
from licensing.services import OrganizationService
from orders.models import Order
from payments.models import PaymentAttempt
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
