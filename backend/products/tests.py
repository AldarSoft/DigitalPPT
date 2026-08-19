from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from products.models import Category, Product
from products.serializers import ProductSerializer, ProductWriteSerializer


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
