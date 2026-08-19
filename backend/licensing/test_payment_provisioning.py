from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from licensing.models import (
    License,
    LicenseEvent,
    LicenseOrderItemProvisioning,
    Organization,
    OrganizationMembership,
    ProductLicenseAllocation,
)
from licensing.services import LicenseLifecycleService, OrganizationService
from orders.models import Order, OrderItem
from payments.models import PaymentAttempt, PaymentProvider
from payments.services import PaymentService
from products.models import Category, Product


class PaymentSuccessProvisioningTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(
            username="license-payment@example.com",
            email="license-payment@example.com",
            password="StrongPass123!",
        )
        self.provider, _ = PaymentProvider.objects.get_or_create(
            code=PaymentProvider.Code.STRIPE,
            defaults={"display_name": "Stripe", "test_mode": True},
        )
        license_category = Category.objects.create(name="Payment licenses")
        radio_category = Category.objects.create(name="Payment radios")
        self.license_product = Product.objects.create(
            category=license_category,
            name="Payment Business License",
            sku="PAY-LIC-200",
            price="250.00",
            inventory_quantity=0,
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=200,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )
        self.radio = Product.objects.create(
            category=radio_category,
            name="Payment Radio",
            sku="PAY-LICENSED-RADIO",
            price="100.00",
            inventory_quantity=5,
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.license_product,
            status=Product.Status.PUBLISHED,
        )

    def create_order(self, *, include_license=True):
        total = "450.00" if include_license else "200.00"
        order = Order.objects.create(
            user=self.customer,
            source=Order.Source.DIRECT,
            customer_first_name="License",
            customer_last_name="Customer",
            customer_email=self.customer.email,
            company_name="Payment License Organization",
            shipping_address="1 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal=total,
            total=total,
        )
        radio_item = OrderItem.objects.create(
            order=order,
            product=self.radio,
            product_name=self.radio.name,
            sku=self.radio.sku,
            unit_price="100.00",
            quantity=2,
            line_total="200.00",
        )
        license_item = None
        if include_license:
            license_item = OrderItem.objects.create(
                order=order,
                product=self.license_product,
                product_name=self.license_product.name,
                sku=self.license_product.sku,
                unit_price="250.00",
                quantity=1,
                line_total="250.00",
            )
        attempt = PaymentAttempt.objects.create(
            order=order,
            provider=self.provider,
            amount=total,
            currency="USD",
            status=PaymentAttempt.Status.PENDING,
            is_test=True,
            created_by=self.customer,
        )
        return order, radio_item, license_item, attempt

    def create_license_only_order(self, *, quantity=1):
        total = str(250 * quantity)
        order = Order.objects.create(
            user=self.customer,
            source=Order.Source.DIRECT,
            customer_first_name="License",
            customer_last_name="Customer",
            customer_email=self.customer.email,
            company_name="Payment License Organization",
            shipping_address="1 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal=total,
            total=total,
        )
        license_item = OrderItem.objects.create(
            order=order,
            product=self.license_product,
            product_name=self.license_product.name,
            sku=self.license_product.sku,
            unit_price="250.00",
            quantity=quantity,
            line_total=total,
        )
        attempt = PaymentAttempt.objects.create(
            order=order,
            provider=self.provider,
            amount=total,
            currency="USD",
            status=PaymentAttempt.Status.PENDING,
            is_test=True,
            created_by=self.customer,
        )
        return order, license_item, attempt

    def test_successful_payment_provisions_license_and_allocates_products(self):
        order, radio_item, license_item, attempt = self.create_order()

        result = PaymentService.simulate_checkout(
            attempt=attempt,
            user=self.customer,
            outcome=PaymentAttempt.Status.SUCCEEDED,
        )

        order.refresh_from_db()
        self.radio.refresh_from_db()
        result.refresh_from_db()
        organization = Organization.objects.get()
        license = License.objects.get(source_order_item=license_item)
        allocation = ProductLicenseAllocation.objects.get(order_item=radio_item)
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(self.radio.inventory_quantity, 3)
        self.assertTrue(
            OrganizationMembership.objects.filter(
                organization=organization,
                user=self.customer,
                role=OrganizationMembership.Role.OWNER,
                is_active=True,
            ).exists()
        )
        self.assertEqual(license.capacity, 200)
        self.assertEqual(license.used_capacity, 2)
        self.assertEqual(allocation.quantity, 2)
        self.assertEqual(allocation.product, self.radio)
        self.assertEqual(
            LicenseEvent.objects.filter(
                license=license,
                event_type=LicenseEvent.Type.PROVISIONED,
            ).count(),
            1,
        )
        self.assertEqual(
            LicenseEvent.objects.filter(
                license=license,
                event_type=LicenseEvent.Type.ALLOCATED,
            ).count(),
            1,
        )
        self.assertEqual(
            result.metadata["license_provisioning"]["status"],
            "completed",
        )

    def test_paid_product_quantity_splits_across_compatible_licenses(self):
        organization = OrganizationService.create(
            name="Existing Capacity Organization",
            owner=self.customer,
            billing_email=self.customer.email,
        )
        existing_license = LicenseLifecycleService.provision(
            organization=organization,
            license_product=self.license_product,
            actor=self.customer,
        )
        License.objects.filter(pk=existing_license.pk).update(used_capacity=199)
        order, radio_item, _, attempt = self.create_order()
        OrderItem.objects.filter(pk=radio_item.pk).update(
            quantity=3,
            line_total="300.00",
        )
        Order.objects.filter(pk=order.pk).update(
            subtotal="550.00",
            total="550.00",
        )
        PaymentAttempt.objects.filter(pk=attempt.pk).update(amount="550.00")

        PaymentService.simulate_checkout(
            attempt=attempt,
            user=self.customer,
            outcome=PaymentAttempt.Status.SUCCEEDED,
        )

        existing_license.refresh_from_db()
        created_license = License.objects.exclude(pk=existing_license.pk).get()
        allocations = {
            allocation.license_id: allocation.quantity
            for allocation in ProductLicenseAllocation.objects.filter(
                order_item=radio_item,
                status=ProductLicenseAllocation.Status.ACTIVE,
            )
        }
        self.assertEqual(allocations[existing_license.pk], 1)
        self.assertEqual(allocations[created_license.pk], 2)
        self.assertEqual(sum(allocations.values()), 3)
        self.assertEqual(existing_license.used_capacity, 200)
        self.assertEqual(created_license.used_capacity, 2)

    def test_repeated_success_callback_is_idempotent(self):
        _, _, _, attempt = self.create_order()
        first = PaymentService.simulate_checkout(
            attempt=attempt,
            user=self.customer,
            outcome=PaymentAttempt.Status.SUCCEEDED,
        )
        counts = (
            Organization.objects.count(),
            License.objects.count(),
            ProductLicenseAllocation.objects.count(),
            LicenseEvent.objects.count(),
            LicenseOrderItemProvisioning.objects.count(),
        )
        PaymentAttempt.objects.filter(pk=first.pk).update(metadata={})
        first.refresh_from_db()

        repeated = PaymentService.simulate_checkout(
            attempt=first,
            user=self.customer,
            outcome=PaymentAttempt.Status.SUCCEEDED,
        )

        self.assertEqual(repeated.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(
            counts,
            (
                Organization.objects.count(),
                License.objects.count(),
                ProductLicenseAllocation.objects.count(),
                LicenseEvent.objects.count(),
                LicenseOrderItemProvisioning.objects.count(),
            ),
        )
        self.assertEqual(LicenseOrderItemProvisioning.objects.count(), 2)

    def test_successful_purchaser_reuses_existing_organization(self):
        existing_organization = OrganizationService.create(
            name="Existing Customer Organization",
            owner=self.customer,
            billing_email=self.customer.email,
        )
        _, _, _, attempt = self.create_order()

        result = PaymentService.simulate_checkout(
            attempt=attempt,
            user=self.customer,
            outcome=PaymentAttempt.Status.SUCCEEDED,
        )

        result.refresh_from_db()
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(
            result.metadata["license_provisioning"]["organization_id"],
            existing_organization.pk,
        )
        self.assertEqual(
            OrganizationMembership.objects.filter(
                organization=existing_organization,
                user=self.customer,
                role=OrganizationMembership.Role.OWNER,
                is_active=True,
            ).count(),
            1,
        )

    def test_license_only_order_extends_assigned_compatible_license(self):
        organization = OrganizationService.create(
            name="Existing Customer Organization",
            owner=self.customer,
            billing_email=self.customer.email,
        )
        existing_license = LicenseLifecycleService.provision(
            organization=organization,
            license_product=self.license_product,
            actor=self.customer,
        )
        License.objects.filter(pk=existing_license.pk).update(used_capacity=2)
        existing_license.refresh_from_db()
        previous_expiry = existing_license.expires_on
        _, license_item, attempt = self.create_license_only_order()

        result = PaymentService.simulate_checkout(
            attempt=attempt,
            user=self.customer,
            outcome=PaymentAttempt.Status.SUCCEEDED,
        )

        result.refresh_from_db()
        existing_license.refresh_from_db()
        renewal_event = LicenseEvent.objects.get(
            license=existing_license,
            event_type=LicenseEvent.Type.RENEWED,
        )
        self.assertEqual(License.objects.count(), 1)
        self.assertEqual(
            existing_license.expires_on,
            previous_expiry + timedelta(days=365),
        )
        self.assertEqual(existing_license.used_capacity, 2)
        self.assertEqual(
            renewal_event.metadata["source_order_item_id"],
            license_item.pk,
        )
        self.assertEqual(
            result.metadata["license_provisioning"]["renewed_license_ids"],
            [existing_license.pk],
        )
        self.assertEqual(
            result.metadata["license_provisioning"]["license_ids"],
            [],
        )
        renewed_expiry = existing_license.expires_on
        renewal_event_count = LicenseEvent.objects.filter(
            license=existing_license,
            event_type=LicenseEvent.Type.RENEWED,
        ).count()
        PaymentAttempt.objects.filter(pk=result.pk).update(metadata={})
        result.refresh_from_db()

        PaymentService.simulate_checkout(
            attempt=result,
            user=self.customer,
            outcome=PaymentAttempt.Status.SUCCEEDED,
        )

        existing_license.refresh_from_db()
        self.assertEqual(existing_license.expires_on, renewed_expiry)
        self.assertEqual(
            LicenseEvent.objects.filter(
                license=existing_license,
                event_type=LicenseEvent.Type.RENEWED,
            ).count(),
            renewal_event_count,
        )
        self.assertEqual(LicenseOrderItemProvisioning.objects.count(), 1)

    def test_license_only_order_creates_unused_license_without_assignment(self):
        _, license_item, attempt = self.create_license_only_order()

        result = PaymentService.simulate_checkout(
            attempt=attempt,
            user=self.customer,
            outcome=PaymentAttempt.Status.SUCCEEDED,
        )

        result.refresh_from_db()
        created_license = License.objects.get(source_order_item=license_item)
        self.assertEqual(created_license.used_capacity, 0)
        self.assertEqual(created_license.available_capacity, 200)
        self.assertEqual(
            result.metadata["license_provisioning"]["license_ids"],
            [created_license.pk],
        )
        self.assertEqual(
            result.metadata["license_provisioning"]["renewed_license_ids"],
            [],
        )

    def test_provisioning_failure_rolls_back_payment_order_and_inventory(self):
        order, _, _, attempt = self.create_order(include_license=False)

        with self.assertRaises(ValidationError):
            PaymentService.simulate_checkout(
                attempt=attempt,
                user=self.customer,
                outcome=PaymentAttempt.Status.SUCCEEDED,
            )

        attempt.refresh_from_db()
        order.refresh_from_db()
        self.radio.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(order.stock_deducted)
        self.assertEqual(self.radio.inventory_quantity, 5)
        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(License.objects.count(), 0)
        self.assertEqual(ProductLicenseAllocation.objects.count(), 0)
