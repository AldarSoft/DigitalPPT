import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from licensing.models import (
    License,
    LicenseCoverageQuoteTarget,
    LicenseOrderItemProvisioning,
    Organization,
    ProductLicenseAllocation,
)
from licensing.services import CoverageQuoteService, OrganizationService
from orders.models import Order, OrderItem
from payments.models import PaymentAttempt, PaymentProvider
from payments.services import PaymentService
from products.models import Category, Product
from quotes.models import QuoteRequest
from quotes.serializers import QuoteRequestCreateSerializer
from quotes.services import QuoteService


@override_settings(DEBUG=True)
class CoverageQuoteTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(
            username="coverage-owner@example.com",
            email="coverage-owner@example.com",
            password="StrongPass123!",
            first_name="Coverage",
            last_name="Owner",
        )
        self.outsider = User.objects.create_user(
            username="coverage-outsider@example.com",
            email="coverage-outsider@example.com",
            password="StrongPass123!",
        )
        self.staff = User.objects.create_user(
            username="coverage-staff@example.com",
            email="coverage-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.organization = OrganizationService.create(
            name="Coverage Customer",
            owner=self.customer,
            billing_email=self.customer.email,
        )
        license_category = Category.objects.create(name="Coverage licenses")
        radio_category = Category.objects.create(name="Coverage radios")
        self.plan = Product.objects.create(
            category=license_category,
            name="Annual Radio Coverage",
            sku="COVERAGE-365",
            price="120.00",
            inventory_quantity=0,
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_term_days=365,
            license_billing_model=Product.LicenseBillingModel.PER_RADIO,
            status=Product.Status.PUBLISHED,
        )
        self.radio = Product.objects.create(
            category=radio_category,
            name="Covered POC Radio",
            sku="COVERED-POC-RADIO",
            price="430.00",
            inventory_quantity=20,
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.plan,
            status=Product.Status.PUBLISHED,
        )
        self.historical_order = Order.objects.create(
            user=self.customer,
            organization=self.organization,
            source=Order.Source.DIRECT,
            status=Order.Status.COMPLETED,
            customer_first_name="Coverage",
            customer_last_name="Owner",
            customer_email=self.customer.email,
            company_name=self.organization.name,
            shipping_address="1 Radio Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal="1720.00",
            total="1720.00",
        )
        self.radio_item = OrderItem.objects.create(
            order=self.historical_order,
            product=self.radio,
            product_name=self.radio.name,
            sku=self.radio.sku,
            unit_price="430.00",
            quantity=4,
            line_total="1720.00",
        )
        LicenseOrderItemProvisioning.objects.create(
            organization=self.organization,
            order_item=self.radio_item,
            operation=LicenseOrderItemProvisioning.Operation.PRODUCT_ALLOCATION,
            allocation_ids=[],
        )
        self.client = APIClient()
        self.media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        self.private_media = override_settings(PRIVATE_MEDIA_ROOT=self.media_dir.name)
        self.private_media.enable()
        self.addCleanup(self.private_media.disable)

    def test_customer_can_quote_only_their_uncovered_radios(self):
        self.client.force_authenticate(self.customer)
        options_url = reverse("licensing-coverage-quote-options")
        response = self.client.get(
            options_url,
            {"organization": self.organization.pk, "license_product": self.plan.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["available_quantity"], 4)
        self.assertEqual(response.data["candidates"][0]["order_item_id"], self.radio_item.pk)

        response = self.client.post(
            reverse("licensing-coverage-quote-create"),
            {
                "organization_id": self.organization.pk,
                "license_product_id": self.plan.pk,
                "targets": [{"order_item_id": self.radio_item.pk, "quantity": 3}],
                "notes": "Cover the radios already deployed to the field.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        quote = QuoteRequest.objects.get()
        self.assertEqual(quote.user, self.customer)
        self.assertEqual(quote.items.get().product, self.plan)
        self.assertEqual(quote.items.get().quantity, 3)
        target = LicenseCoverageQuoteTarget.objects.get()
        self.assertEqual(target.organization, self.organization)
        self.assertEqual(target.order_item, self.radio_item)
        self.assertEqual(target.quantity, 3)
        self.assertEqual(License.objects.count(), 0)
        self.assertEqual(PaymentAttempt.objects.count(), 0)

        response = self.client.get(
            options_url,
            {"organization": self.organization.pk, "license_product": self.plan.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["available_quantity"], 1)
        self.assertEqual(response.data["candidates"][0]["available_quantity"], 1)

        response = self.client.post(
            reverse("licensing-coverage-quote-create"),
            {
                "organization_id": self.organization.pk,
                "license_product_id": self.plan.pk,
                "targets": [{"order_item_id": self.radio_item.pk, "quantity": 2}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_member_cannot_view_coverage_candidates(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.get(
            reverse("licensing-coverage-quote-options"),
            {"organization": self.organization.pk, "license_product": self.plan.pk},
        )

        self.assertEqual(response.status_code, 403)

    def test_generic_quote_rejects_standalone_per_radio_quantity(self):
        serializer = QuoteRequestCreateSerializer(
            data={
                "requester_company_name": self.organization.name,
                "requester_contact_person": "Coverage Owner",
                "requester_email": self.customer.email,
                "requester_phone": "+97699112233",
                "notes": "",
                "items": [
                    {
                        "product": self.plan.pk,
                        "quantity": 4,
                        "specifications": {},
                    }
                ],
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("Standalone coverage", str(serializer.errors))

    def test_generic_quote_requires_matching_per_radio_plan_quantity(self):
        base_data = {
            "requester_company_name": self.organization.name,
            "requester_contact_person": "Coverage Owner",
            "requester_email": self.customer.email,
            "requester_phone": "+97699112233",
            "notes": "",
        }
        missing_plan = QuoteRequestCreateSerializer(
            data={
                **base_data,
                "items": [
                    {"product": self.radio.pk, "quantity": 2, "specifications": {}}
                ],
            }
        )
        matching_plan = QuoteRequestCreateSerializer(
            data={
                **base_data,
                "items": [
                    {"product": self.radio.pk, "quantity": 2, "specifications": {}},
                    {"product": self.plan.pk, "quantity": 2, "specifications": {}},
                ],
            }
        )

        self.assertFalse(missing_plan.is_valid())
        self.assertTrue(matching_plan.is_valid(), matching_plan.errors)

    def test_confirmed_coverage_invoice_creates_grouped_license_for_selected_radios(self):
        quote = CoverageQuoteService.create_quote(
            user=self.customer,
            organization_id=self.organization.pk,
            license_product_id=self.plan.pk,
            targets=[{"order_item_id": self.radio_item.pk, "quantity": 4}],
        )
        quote = QuoteService.update_status(
            quote_request=quote,
            new_status=QuoteRequest.Status.REVIEWING,
            user=self.staff,
        )
        quote = QuoteService.update_status(
            quote_request=quote,
            new_status=QuoteRequest.Status.QUOTE_APPROVED,
            user=self.staff,
        )
        quote_item = quote.items.get()
        quote = QuoteService.issue_invoice(
            quote_request=quote,
            user=self.staff,
            item_prices=[
                {"id": quote_item.pk, "quoted_unit_price": Decimal("120.00")}
            ],
            shipping=Decimal("0.00"),
            admin_message="Annual coverage for four existing radios.",
        )
        invoice_order = quote.orders.get()
        self.assertEqual(invoice_order.organization, self.organization)
        self.assertEqual(invoice_order.total, Decimal("480.00"))

        provider, _ = PaymentProvider.objects.get_or_create(
            code=PaymentProvider.Code.BANK_TRANSFER,
            defaults={"display_name": "Bank transfer"},
        )
        provider.is_enabled = True
        provider.is_customer_available = False
        provider.test_mode = False
        provider.save(
            update_fields=["is_enabled", "is_customer_available", "test_mode", "updated_at"]
        )
        attempt = PaymentService.confirm_bank_transfer(
            order=invoice_order,
            actor=self.staff,
            bank_transaction_reference="COVERAGE-QUOTE-0001",
        )

        attempt.refresh_from_db()
        quote.refresh_from_db()
        grouped_license = License.objects.get()
        allocation = ProductLicenseAllocation.objects.get()
        invoice_license_item = invoice_order.items.get(product=self.plan)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(quote.status, QuoteRequest.Status.PAYMENT_CONFIRMED)
        self.assertEqual(grouped_license.organization, self.organization)
        self.assertEqual(grouped_license.source_order_item, invoice_license_item)
        self.assertEqual(grouped_license.capacity, 4)
        self.assertEqual(grouped_license.used_capacity, 4)
        self.assertEqual(allocation.license, grouped_license)
        self.assertEqual(allocation.order_item, self.radio_item)
        self.assertEqual(allocation.quantity, 4)
