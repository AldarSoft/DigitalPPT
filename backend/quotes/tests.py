import tempfile
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from quotes.invoice_pdf import build_invoice_pdf
from quotes.models import QuoteRequest


class InvoicePdfBankTransferTests(SimpleTestCase):
    def test_bank_instructions_do_not_depend_on_payment_provider_availability(self):
        site_settings = SimpleNamespace(
            site_name="Digital PTT",
            default_currency="USD",
            support_email="support@example.com",
            bank_transfer_is_configured=True,
            bank_beneficiary_name="Digital PTT",
            bank_name="Sample Bank",
            bank_account_number="0000000000000000",
            bank_iban="SAMPLE-IBAN-000023",
            bank_swift_bic="SAMPBANK",
            bank_payment_instructions="Use the invoice number as the payment reference.",
        )
        quote_request = SimpleNamespace(
            invoice_number="INV-2026-000028",
            quote_number="QTE-2026-000028",
            invoiced_at=datetime(2026, 8, 31),
            requester_contact_person="Test Customer",
            requester_company_name="Test Company",
            requester_email="customer@example.com",
            requester_phone="99999999",
            admin_message="",
            quoted_subtotal=Decimal("1360.00"),
            quoted_shipping=Decimal("50.00"),
            quoted_total=Decimal("1410.00"),
            items=SimpleNamespace(all=lambda: []),
        )

        pdf = build_invoice_pdf(
            quote_request=quote_request,
            site_settings=site_settings,
        )

        self.assertTrue(pdf.startswith(b"%PDF"))


class InvoicePdfPrivacyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="invoice-owner@example.com",
            email="invoice-owner@example.com",
            password="StrongPass123!",
        )
        self.other = User.objects.create_user(
            username="invoice-other@example.com",
            email="invoice-other@example.com",
            password="StrongPass123!",
        )
        self.staff = User.objects.create_user(
            username="invoice-staff@example.com",
            email="invoice-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        self.settings_override = override_settings(
            PRIVATE_MEDIA_ROOT=self.media_dir.name,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.quote = QuoteRequest.objects.create(
            user=self.owner,
            requester_contact_person="Invoice Owner",
            requester_email=self.owner.email,
            status=QuoteRequest.Status.INVOICE_SENT,
            invoice_pdf=SimpleUploadedFile(
                "invoice.pdf",
                b"%PDF-1.4 private invoice",
                content_type="application/pdf",
            ),
        )

    def invoice_url(self):
        return f"/api/v1/quotes/{self.quote.quote_number}/invoice-pdf/"

    def test_invoice_pdf_requires_authentication(self):
        response = APIClient().get(self.invoice_url())
        self.assertEqual(response.status_code, 401)

    def test_invoice_pdf_is_hidden_from_other_users(self):
        api = APIClient()
        api.force_authenticate(self.other)
        response = api.get(self.invoice_url())
        self.assertEqual(response.status_code, 404)

    def test_quote_owner_can_download_the_invoice_with_private_headers(self):
        api = APIClient()
        api.force_authenticate(self.owner)
        response = api.get(self.invoice_url())
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertIn("no-store", response["Cache-Control"])
            self.assertIn("private", response["Cache-Control"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        finally:
            response.close()

    def test_authorized_staff_can_download_the_invoice(self):
        api = APIClient()
        api.force_authenticate(self.staff)
        response = api.get(self.invoice_url())
        try:
            self.assertEqual(response.status_code, 200)
        finally:
            response.close()
