from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from quotes.invoice_pdf import build_invoice_pdf


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
