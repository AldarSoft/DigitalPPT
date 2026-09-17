from io import BytesIO, StringIO
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from licensing.models import License, Organization
from orders.models import InventoryReservation, Order, OrderItem
from products.models import Category, InventoryAdjustment, Product
from products.serializers import AdminProductSerializer, ProductSerializer, ProductWriteSerializer
from PIL import Image


class ConfigurePerRadioLicenseCommandTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Licenses")
        self.plan = Product.objects.create(
            category=self.category,
            name="Legacy annual plan",
            sku="LIC-ANNUAL",
            price="1000.00",
            sale_price="900.00",
            bulk_minimum_quantity=5,
            bulk_unit_price="850.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=200,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )

    def test_command_converts_plan_to_fixed_per_radio_pricing(self):
        output = StringIO()

        call_command(
            "configure_per_radio_license",
            sku=self.plan.sku,
            unit_price="120.00",
            term_days=365,
            stdout=output,
        )

        self.plan.refresh_from_db()
        self.assertEqual(
            self.plan.license_billing_model,
            Product.LicenseBillingModel.PER_RADIO,
        )
        self.assertIsNone(self.plan.license_capacity)
        self.assertEqual(self.plan.price, 120)
        self.assertIsNone(self.plan.sale_price)
        self.assertIsNone(self.plan.bulk_minimum_quantity)
        self.assertIsNone(self.plan.bulk_unit_price)
        self.assertIn("Configured LIC-ANNUAL", output.getvalue())

    def test_command_refuses_to_convert_plan_used_by_open_legacy_order(self):
        order = Order.objects.create(
            status=Order.Status.PENDING,
            customer_first_name="Pending",
            customer_last_name="Customer",
            customer_email="pending@example.com",
            shipping_address="1 Test Street",
            shipping_city="Test City",
            shipping_postal_code="10000",
            shipping_country="GB",
        )
        OrderItem.objects.create(
            order=order,
            product=self.plan,
            product_name=self.plan.name,
            sku=self.plan.sku,
            unit_price=self.plan.price,
            quantity=1,
            line_total=self.plan.price,
        )

        with self.assertRaisesMessage(CommandError, order.order_number):
            call_command(
                "configure_per_radio_license",
                sku=self.plan.sku,
                unit_price="120.00",
            )

        self.plan.refresh_from_db()
        self.assertIsNone(self.plan.license_billing_model)
        self.assertEqual(self.plan.license_capacity, 200)
        self.assertEqual(self.plan.price, 1000)

    def test_command_refuses_to_reprice_a_plan_with_issued_legacy_licenses(self):
        organization = Organization.objects.create(name="Legacy Customer")
        license = License.objects.create(
            organization=organization,
            license_product=self.plan,
            name="Existing capacity license",
            status=License.Status.ACTIVE,
            capacity=200,
        )

        with self.assertRaisesMessage(CommandError, license.license_number):
            call_command(
                "configure_per_radio_license",
                sku=self.plan.sku,
                unit_price="120.00",
            )

        self.plan.refresh_from_db()
        self.assertIsNone(self.plan.license_billing_model)
        self.assertEqual(self.plan.license_capacity, 200)
        self.assertEqual(self.plan.price, 1000)


class CategoryManagementApiTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="category-admin",
            email="category-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def test_staff_can_create_update_and_delete_an_empty_category(self):
        created = self.api.post(
            "/api/v1/products/categories/",
            {
                "name": "Vehicle Radios",
                "slug": "vehicle-radios",
                "description": "Vehicle-mounted radio products.",
                "image_url": "",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)

        updated = self.api.put(
            "/api/v1/products/categories/vehicle-radios/",
            {
                "name": "Vehicle and Base Stations",
                "slug": "vehicle-base-stations",
                "description": "Vehicle-mounted and fixed-location equipment.",
                "image_url": "",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["slug"], "vehicle-base-stations")

        deleted = self.api.delete(
            "/api/v1/products/categories/vehicle-base-stations/"
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Category.objects.filter(slug="vehicle-base-stations").exists())

    def test_category_with_products_cannot_be_deleted(self):
        category = Category.objects.create(name="POC Radios", slug="poc-radios")
        Product.objects.create(
            category=category,
            name="IPTT Test Radio",
            sku="IPTT-TEST",
            price="100.00",
        )

        response = self.api.delete("/api/v1/products/categories/poc-radios/")

        self.assertEqual(response.status_code, 409)
        self.assertIn("products", response.data["detail"])
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

    def test_inactive_categories_are_hidden_only_from_public_catalog(self):
        Category.objects.create(name="Active category", is_active=True)
        Category.objects.create(name="Inactive category", is_active=False)

        public_response = APIClient().get("/api/v1/products/categories/")
        public_categories = public_response.data.get("results", public_response.data)
        staff_response = self.api.get("/api/v1/products/categories/?workspace=admin")
        staff_categories = staff_response.data.get("results", staff_response.data)

        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(
            {category["name"] for category in public_categories},
            {"Active category"},
        )
        self.assertEqual(
            {category["name"] for category in staff_categories},
            {"Active category", "Inactive category"},
        )


class ProductInventoryPrivacyTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Privacy Catalog")
        self.product = Product.objects.create(
            category=self.category,
            name="Privacy Radio",
            sku="PRIV-RADIO",
            price="250.00",
            inventory_quantity=5,
            status=Product.Status.PUBLISHED,
        )
        self.staff = get_user_model().objects.create_user(
            username="privacy-staff",
            email="privacy-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )

    def test_public_product_responses_omit_operational_inventory_fields(self):
        response = APIClient().get("/api/v1/products/catalog/privacy-radio/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["inventory_quantity"], 5)
        for field in (
            "on_hand_inventory_quantity",
            "reserved_inventory_quantity",
            "backordered_inventory_quantity",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ):
            self.assertNotIn(field, response.data)

    def test_admin_product_responses_include_exact_inventory_fields(self):
        api = APIClient()
        api.force_authenticate(self.staff)
        response = api.get("/api/v1/products/catalog/privacy-radio/?workspace=admin")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["on_hand_inventory_quantity"], 5)
        self.assertEqual(response.data["reserved_inventory_quantity"], 0)
        self.assertEqual(response.data["backordered_inventory_quantity"], 0)
        self.assertEqual(response.data["status"], Product.Status.PUBLISHED)

    def test_serializer_shapes_split_public_and_admin_fields(self):
        public_data = ProductSerializer(self.product).data
        admin_data = AdminProductSerializer(self.product).data

        self.assertNotIn("on_hand_inventory_quantity", public_data)
        self.assertNotIn("cost_price", public_data)
        self.assertIn("on_hand_inventory_quantity", admin_data)
        self.assertIn("reserved_inventory_quantity", admin_data)
        self.assertIn("status", admin_data)
        self.assertIn("inventory_quantity", public_data)


class ProductImageSecurityTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="image-admin",
            email="image-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def test_upload_decodes_and_reencodes_a_valid_image(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            source = BytesIO()
            Image.new("RGB", (24, 24), (20, 80, 180)).save(source, format="PNG")
            response = self.api.post(
                "/api/v1/products/upload-image/",
                {"image": SimpleUploadedFile("photo.png", source.getvalue(), content_type="image/png")},
                format="multipart",
            )
            self.assertEqual(response.status_code, 201)
            self.assertTrue(response.data["image_url"].endswith(".png"))

    def test_upload_rejects_spoofed_image_content(self):
        response = self.api.post(
            "/api/v1/products/upload-image/",
            {"image": SimpleUploadedFile("fake.png", b"not-an-image", content_type="image/png")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)


class ProductLicensingContractTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="POC Radios")
        self.license_category = Category.objects.create(name="Licenses")
        self.license_product = Product.objects.create(
            category=self.license_category,
            name="RadioAdmin Business License",
            sku="LIC-RA-BUS-200",
            price="250.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=200,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )

    def test_product_serializer_exposes_license_contract(self):
        radio = Product.objects.create(
            category=self.category,
            name="IPTT710 Android",
            sku="IPTT710",
            price="430.00",
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.license_product,
            status=Product.Status.PUBLISHED,
        )

        payload = ProductSerializer(radio).data

        self.assertEqual(payload["licensing_role"], "licensed_product")
        self.assertEqual(
            payload["required_license_product"]["sku"], "LIC-RA-BUS-200"
        )
        self.assertEqual(payload["required_license_product"]["license_capacity"], 200)
        self.assertEqual(payload["required_license_product"]["license_term_days"], 365)
        self.assertTrue(payload["is_stock_tracked"])

    def test_license_product_is_not_stock_tracked(self):
        payload = ProductSerializer(self.license_product).data

        self.assertEqual(payload["licensing_role"], "license_product")
        self.assertFalse(payload["is_stock_tracked"])

    def test_public_stock_filter_includes_digital_license_product(self):
        response = APIClient().get(reverse("product-list"), {"stock": "true"})

        self.assertEqual(response.status_code, 200)
        products = response.data.get("results", response.data)
        self.assertIn(self.license_product.sku, {product["sku"] for product in products})

    def test_per_radio_plan_is_visible_in_catalog_and_included_with_radio(self):
        self.license_product.license_billing_model = Product.LicenseBillingModel.PER_RADIO
        self.license_product.license_capacity = None
        self.license_product.price = "120.00"
        self.license_product.save(
            update_fields=["license_billing_model", "license_capacity", "price", "updated_at"]
        )
        radio = Product.objects.create(
            category=self.category,
            name="Annual license radio",
            sku="ANNUAL-RADIO",
            price="430.00",
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.license_product,
            status=Product.Status.PUBLISHED,
        )

        response = APIClient().get(reverse("product-list"))

        self.assertEqual(response.status_code, 200)
        products = response.data.get("results", response.data)
        by_sku = {product["sku"]: product for product in products}
        self.assertIn(self.license_product.sku, by_sku)
        self.assertEqual(
            by_sku[self.license_product.sku]["license_billing_model"],
            Product.LicenseBillingModel.PER_RADIO,
        )
        self.assertEqual(
            by_sku[radio.sku]["required_license_product"]["license_billing_model"],
            Product.LicenseBillingModel.PER_RADIO,
        )

    def test_write_serializer_accepts_per_radio_plan_without_capacity(self):
        serializer = ProductWriteSerializer(
            data={
                "category": self.license_category.pk,
                "name": "Annual per-radio license",
                "sku": "ANNUAL-PER-RADIO",
                "price": "120.00",
                "licensing_role": "license_product",
                "license_billing_model": "per_radio",
                "license_capacity": None,
                "license_term_days": 365,
                "status": "published",
                "is_active": True,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save()
        self.assertIsNone(product.license_capacity)
        self.assertEqual(product.license_billing_model, Product.LicenseBillingModel.PER_RADIO)

    def test_write_serializer_rejects_discounts_on_per_radio_plan(self):
        serializer = ProductWriteSerializer(
            data={
                "category": self.license_category.pk,
                "name": "Discounted annual license",
                "sku": "DISCOUNTED-PER-RADIO",
                "price": "120.00",
                "sale_price": "100.00",
                "licensing_role": "license_product",
                "license_billing_model": "per_radio",
                "license_capacity": None,
                "license_term_days": 365,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("price", serializer.errors)

    def test_write_serializer_protects_billing_model_after_license_is_issued(self):
        organization = Organization.objects.create(name="Existing Customer")
        License.objects.create(
            organization=organization,
            license_product=self.license_product,
            name="Existing capacity license",
            status=License.Status.ACTIVE,
            capacity=200,
        )
        self.license_product.refresh_from_db()
        serializer = ProductWriteSerializer(
            self.license_product,
            data={
                "license_billing_model": "per_radio",
                "license_capacity": None,
                "sale_price": None,
                "bulk_minimum_quantity": None,
                "bulk_unit_price": None,
            },
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("license_billing_model", serializer.errors)

    def test_write_serializer_accepts_compatible_license_product(self):
        serializer = ProductWriteSerializer(
            data={
                "category": self.category.pk,
                "name": "IPTT810 / IPTT820",
                "sku": "IPTT810",
                "price": "430.00",
                "inventory_quantity": 10,
                "licensing_role": "licensed_product",
                "required_license_product_id": self.license_product.pk,
                "status": "published",
                "is_active": True,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save()
        self.assertEqual(product.required_license_product, self.license_product)

    def test_write_serializer_rejects_non_license_compatibility_target(self):
        standard_product = Product.objects.create(
            category=self.category,
            name="Standard radio",
            sku="STANDARD",
            price="100.00",
        )
        serializer = ProductWriteSerializer(
            data={
                "category": self.category.pk,
                "name": "Licensed radio",
                "sku": "LICENSED",
                "price": "100.00",
                "licensing_role": "licensed_product",
                "required_license_product_id": standard_product.pk,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("required_license_product_id", serializer.errors)

    def test_model_validation_rejects_incomplete_license_product(self):
        product = Product(
            category=self.license_category,
            name="Incomplete license",
            sku="LIC-INCOMPLETE",
            price="10.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
        )

        with self.assertRaises(ValidationError) as raised:
            product.full_clean()

        self.assertIn("license_capacity", raised.exception.message_dict)
        self.assertIn("license_term_days", raised.exception.message_dict)


class InventoryAdjustmentTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="inventory-admin",
            email="inventory-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        category = Category.objects.create(name="Inventory")
        self.product = Product.objects.create(
            category=category,
            name="Reserved radio",
            sku="RESERVED-RADIO",
            price="100.00",
            inventory_quantity=8,
            status=Product.Status.PUBLISHED,
        )
        order = Order.objects.create(
            user=self.staff,
            customer_first_name="Inventory",
            customer_last_name="Admin",
            customer_email=self.staff.email,
            shipping_address="1 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal="800.00",
            total="800.00",
        )
        item = OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price="100.00",
            quantity=8,
            reserved_quantity=8,
            fulfillment_status=OrderItem.FulfillmentStatus.READY,
            line_total="800.00",
        )
        InventoryReservation.objects.create(order_item=item, product=self.product, quantity=8)
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def test_counted_stock_cannot_be_lower_than_paid_reservations(self):
        response = self.api.post(
            f"/api/v1/products/catalog/{self.product.slug}/inventory-adjust/",
            {"mode": "set", "quantity": 1, "reason": "warehouse_count"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 8)

    def test_add_stock_records_an_audited_adjustment(self):
        response = self.api.post(
            f"/api/v1/products/catalog/{self.product.slug}/inventory-adjust/",
            {"mode": "add", "quantity": 2, "reason": "stock_received"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        adjustment = InventoryAdjustment.objects.get(product=self.product)
        self.assertEqual(self.product.inventory_quantity, 10)
        self.assertEqual(adjustment.quantity_before, 8)
        self.assertEqual(adjustment.quantity_after, 10)
        self.assertEqual(adjustment.performed_by, self.staff)
