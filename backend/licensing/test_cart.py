from uuid import uuid4

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from licensing.models import License
from licensing.services import LicenseLifecycleService, OrganizationService
from orders.models import Order
from orders.services import OrderService
from products.models import Category, Product


class CartLicenseIntegrationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cart-license@example.com",
            email="cart-license@example.com",
            password="StrongPass123!",
        )
        self.organization = OrganizationService.create(
            name="Cart License Organization",
            owner=self.user,
        )
        license_category = Category.objects.create(name="Cart Licenses")
        radio_category = Category.objects.create(name="Cart Radios")
        self.license_product = Product.objects.create(
            category=license_category,
            name="Cart Business License",
            sku="CART-LIC-3",
            price="50.00",
            inventory_quantity=0,
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=3,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )
        self.radio = Product.objects.create(
            category=radio_category,
            name="Cart Radio",
            sku="CART-RADIO",
            price="100.00",
            inventory_quantity=20,
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.license_product,
            status=Product.Status.PUBLISHED,
        )

    def cart_payload(self, items):
        return {"items": items}

    def checkout_payload(self, items):
        return {
            "idempotency_key": str(uuid4()),
            "customer_first_name": "Cart",
            "customer_last_name": "Customer",
            "customer_email": self.user.email,
            "customer_phone": "99999999",
            "company_name": "Cart License Organization",
            "shipping_address": "1 Main Street",
            "shipping_city": "Ulaanbaatar",
            "shipping_state": "",
            "shipping_postal_code": "14200",
            "shipping_country": "Mongolia",
            "notes": "",
            "items": items,
        }

    def test_anonymous_cart_adds_capacity_without_using_organization_licenses(self):
        response = self.client.post(
            "/api/v1/licensing/cart-capacity/",
            self.cart_payload([{"product": self.radio.pk, "quantity": 4}]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["organization"])
        requirement = response.data["requirements"][0]
        self.assertEqual(requirement["uncovered_quantity"], 4)
        self.assertEqual(requirement["required_license_units"], 2)
        self.assertEqual(requirement["automatic_license_units"], 2)
        self.assertEqual(requirement["license_product"]["id"], self.license_product.pk)

    def test_authenticated_cart_uses_existing_available_capacity_first(self):
        license = LicenseLifecycleService.provision(
            organization=self.organization,
            license_product=self.license_product,
        )
        License.objects.filter(pk=license.pk).update(used_capacity=1)
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/v1/licensing/cart-capacity/",
            self.cart_payload([{"product": self.radio.pk, "quantity": 4}]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        requirement = response.data["requirements"][0]
        self.assertEqual(requirement["available_capacity"], 2)
        self.assertEqual(requirement["covered_quantity"], 2)
        self.assertEqual(requirement["uncovered_quantity"], 2)
        self.assertEqual(requirement["automatic_license_units"], 1)

    def test_manual_license_product_reduces_automatic_quantity(self):
        response = self.client.post(
            "/api/v1/licensing/cart-capacity/",
            self.cart_payload(
                [
                    {"product": self.radio.pk, "quantity": 4},
                    {"product": self.license_product.pk, "quantity": 1},
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        requirement = response.data["requirements"][0]
        self.assertEqual(requirement["required_license_units"], 2)
        self.assertEqual(requirement["provided_license_units"], 1)
        self.assertEqual(requirement["automatic_license_units"], 1)

    def test_checkout_adds_omitted_required_license_products(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/v1/orders/checkout/",
            self.checkout_payload([{"product": self.radio.pk, "quantity": 4}]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(order_number=response.data["order_number"])
        quantities = {item.product_id: item.quantity for item in order.items.all()}
        self.assertEqual(quantities[self.radio.pk], 4)
        self.assertEqual(quantities[self.license_product.pk], 2)
        self.assertEqual(order.subtotal, 500)

        OrderService.update_status(order=order, new_status=Order.Status.PROCESSING)
        self.radio.refresh_from_db()
        self.license_product.refresh_from_db()
        self.assertEqual(self.radio.inventory_quantity, 16)
        self.assertEqual(self.license_product.inventory_quantity, 0)

    def test_checkout_discards_stale_automatic_license_when_capacity_covers_cart(self):
        LicenseLifecycleService.provision(
            organization=self.organization,
            license_product=self.license_product,
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/v1/orders/checkout/",
            self.checkout_payload(
                [
                    {"product": self.radio.pk, "quantity": 2},
                    {
                        "product": self.license_product.pk,
                        "quantity": 1,
                        "automatic": True,
                    },
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(order_number=response.data["order_number"])
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.get().product, self.radio)
        self.assertEqual(order.subtotal, 200)

    def test_checkout_preserves_manual_license_and_does_not_duplicate_it(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            "/api/v1/orders/checkout/",
            self.checkout_payload(
                [
                    {"product": self.radio.pk, "quantity": 2},
                    {
                        "product": self.license_product.pk,
                        "quantity": 1,
                        "automatic": False,
                    },
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(order_number=response.data["order_number"])
        quantities = {item.product_id: item.quantity for item in order.items.all()}
        self.assertEqual(quantities[self.radio.pk], 2)
        self.assertEqual(quantities[self.license_product.pk], 1)
        self.assertEqual(order.subtotal, 250)
