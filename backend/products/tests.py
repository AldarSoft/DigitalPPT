from io import BytesIO
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from orders.models import InventoryReservation, Order, OrderItem
from products.models import Category, InventoryAdjustment, Product
from products.serializers import ProductSerializer, ProductWriteSerializer
from PIL import Image


class ProductImageSecurityTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="image-admin",
            email="image-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
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
