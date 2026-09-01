import json
import re
import tempfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from decimal import Decimal
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core import mail, signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from PIL import Image

from products.models import Category, Product, ProductImage, ProductSpecification
from quotes.models import QuoteRequest
from quotes.claims import make_guest_quote_claim_token
from orders.models import Order
from payments.models import PaymentAttempt, PaymentProvider
from common.integrations.power_automate import send_power_automate_event
from core.models import NotificationJob, Promotion, UserNotification
from licensing.services import OrganizationService
from users.services import AccountSetupService


class ActiveApiPermissionTests(APITestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.customer = User.objects.create_user(
            username="customer@example.com",
            email="customer@example.com",
            password="StrongPass123!",
        )
        self.admin = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        category = Category.objects.create(name="Server Racks")
        self.product = Product.objects.create(
            category=category,
            name="42U Rack",
            sku="SR-42",
            price="1000.00",
            inventory_quantity=5,
            status=Product.Status.PUBLISHED,
        )
        ProductSpecification.objects.create(
            product=self.product,
            key="Height",
            value="42U",
        )

    def order_payload(self):
        return {
            "idempotency_key": str(uuid4()),
            "customer_first_name": "Test",
            "customer_last_name": "Customer",
            "customer_email": "customer@example.com",
            "customer_phone": "+1 555 000 0000",
            "shipping_address": "123 Main St",
            "shipping_city": "Austin",
            "shipping_country": "US",
            "items": [{"product": self.product.id, "quantity": 1}],
        }

    def quote_payload(self):
        return {
            "requester_company_name": "Example Co",
            "requester_contact_person": "Test Customer",
            "requester_email": "customer@example.com",
            "requester_phone": "+1 555 000 0000",
            "items": [{"product": self.product.id, "quantity": 1}],
        }

    def test_quote_item_suggests_configured_bulk_unit_price(self):
        self.product.bulk_minimum_quantity = 3
        self.product.bulk_unit_price = Decimal("850.00")
        self.product.save(update_fields=["bulk_minimum_quantity", "bulk_unit_price", "updated_at"])
        payload = self.quote_payload()
        payload["items"][0]["quantity"] = 3

        response = self.client.post("/api/v1/quotes/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["items"][0]["suggested_unit_price"], Decimal("850.00"))
        self.assertTrue(response.data["items"][0]["bulk_price_applied"])

    def test_anonymous_user_cannot_create_order(self):
        response = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_cannot_create_order(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_can_log_in(self):
        response = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "customer@example.com", "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["user"]["is_staff"])

    def test_customer_can_log_in_with_mixed_case_email(self):
        response = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "Customer@Example.COM", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["user"]["is_staff"])

    def test_customer_can_log_in_when_an_existing_account_stored_a_mixed_case_email(self):
        legacy_customer = get_user_model().objects.create_user(
            username="legacy-customer",
            email="Legacy.Customer@Example.COM",
            password="StrongPass123!",
        )

        response = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": "legacy.customer@example.com", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], legacy_customer.pk)

    def test_admin_can_request_and_complete_password_reset(self):
        login_response = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": self.admin.email, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(login_response.data["mfa_required"])
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        login_response = self.client.post(
            "/api/v1/users/auth/staff-mfa/",
            {"challenge": login_response.data["challenge"], "code": code},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        previous_access = login_response.data["access"]
        previous_refresh = login_response.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
        mail.outbox.clear()

        request_response = self.client.post(
            "/api/v1/users/auth/password-reset/",
            {"email": self.admin.email},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/auth/reset-password?uid=", mail.outbox[0].body)

        uid = urlsafe_base64_encode(force_bytes(self.admin.pk))
        token = default_token_generator.make_token(self.admin)
        confirm_response = self.client.post(
            "/api/v1/users/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password": "NewStrongPass456!",
                "confirm_password": "NewStrongPass456!",
            },
            format="json",
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_response.cookies[settings.AUTH_REFRESH_COOKIE_NAME]["max-age"], 0)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("NewStrongPass456!"))

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {previous_access}")
        invalid_access = self.client.get("/api/v1/users/auth/me/")
        self.assertEqual(invalid_access.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.credentials()
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = previous_refresh
        invalid_refresh = self.client.post("/api/v1/users/auth/refresh/", {}, format="json")
        self.assertEqual(invalid_refresh.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_can_request_password_reset(self):
        response = self.client.post(
            "/api/v1/users/auth/password-reset/",
            {"email": self.customer.email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_admin_created_account_can_set_its_password_once(self):
        user = AccountSetupService.create_user(
            email="setup-client@example.com",
            first_name="Setup",
            last_name="Client",
        )
        self.assertFalse(user.has_usable_password())

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        payload = {
            "uid": uid,
            "token": token,
            "new_password": "NewStrongPass456!",
            "confirm_password": "NewStrongPass456!",
        }

        first_response = self.client.post(
            "/api/v1/users/auth/password-reset/confirm/",
            payload,
            format="json",
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewStrongPass456!"))

        reused_response = self.client.post(
            "/api/v1/users/auth/password-reset/confirm/",
            payload,
            format="json",
        )
        self.assertEqual(reused_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_customer_creation_queues_a_single_use_setup_email(self):
        self.client.force_authenticate(self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/users/accounts/",
                {
                    "email": "customer-created-by-staff@example.com",
                    "username": "customer-created-by-staff",
                    "first_name": "Created",
                    "last_name": "Customer",
                    "is_customer": True,
                    "is_staff": False,
                    "is_active": True,
                    "profile": {"company_name": "Example Co"},
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["account_setup_email_queued"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Set up your Digital PTT account", mail.outbox[0].subject)
        user = get_user_model().objects.get(email="customer-created-by-staff@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.profile.company_name, "Example Co")

    def test_admin_customer_creation_rejects_a_staff_entered_password(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            "/api/v1/users/accounts/",
            {
                "email": "password-customer@example.com",
                "username": "password-customer",
                "password": "StrongPass123!",
                "is_customer": True,
                "is_staff": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    @override_settings(PASSWORD_RESET_TIMEOUT=60)
    def test_password_reset_rejects_an_expired_token(self):
        issued_at = (timezone.now() - timedelta(minutes=2)).replace(tzinfo=None)
        with patch.object(default_token_generator, "_now", return_value=issued_at):
            token = default_token_generator.make_token(self.customer)

        response = self.client.post(
            "/api/v1/users/auth/password-reset/confirm/",
            {
                "uid": urlsafe_base64_encode(force_bytes(self.customer.pk)),
                "token": token,
                "new_password": "NewStrongPass456!",
                "confirm_password": "NewStrongPass456!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_reset_rejects_an_invalid_token(self):
        response = self.client.post(
            "/api/v1/users/auth/password-reset/confirm/",
            {
                "uid": urlsafe_base64_encode(force_bytes(self.customer.pk)),
                "token": "invalid-token",
                "new_password": "NewStrongPass456!",
                "confirm_password": "NewStrongPass456!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(PASSWORD_RESET_TIMEOUT=60)
    def test_password_reset_rejects_an_expired_token(self):
        issued_at = (timezone.now() - timedelta(minutes=2)).replace(tzinfo=None)
        with patch.object(default_token_generator, "_now", return_value=issued_at):
            token = default_token_generator.make_token(self.customer)

        response = self.client.post(
            "/api/v1/users/auth/password-reset/confirm/",
            {
                "uid": urlsafe_base64_encode(force_bytes(self.customer.pk)),
                "token": token,
                "new_password": "NewStrongPass456!",
                "confirm_password": "NewStrongPass456!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_direct_checkout_uses_server_price(self):
        payload = self.order_payload()
        payload["items"][0]["unit_price"] = "0.01"
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            "/api/v1/orders/checkout/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total"], Decimal("1000.00"))
        self.assertEqual(response.data["items"][0]["unit_price"], Decimal("1000.00"))
        self.assertEqual(response.data["source"], Order.Source.DIRECT)

    def test_checkout_associates_the_selected_organization(self):
        organization = OrganizationService.create(
            name="Selected Checkout Organization",
            owner=self.customer,
            billing_email=self.customer.email,
        )
        payload = self.order_payload()
        payload["organization"] = organization.pk
        self.client.force_authenticate(self.customer)

        response = self.client.post("/api/v1/orders/checkout/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["organization_id"], organization.pk)
        self.assertEqual(Order.objects.get(pk=response.data["id"]).organization, organization)

    def test_customer_direct_checkout_uses_bulk_price_at_threshold(self):
        self.product.bulk_minimum_quantity = 3
        self.product.bulk_unit_price = Decimal("850.00")
        self.product.save(update_fields=["bulk_minimum_quantity", "bulk_unit_price", "updated_at"])
        payload = self.order_payload()
        payload["items"][0]["quantity"] = 3
        self.client.force_authenticate(self.customer)

        response = self.client.post("/api/v1/orders/checkout/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["items"][0]["unit_price"], Decimal("850.00"))
        self.assertEqual(response.data["subtotal"], Decimal("2550.00"))

    def test_direct_checkout_is_idempotent(self):
        payload = self.order_payload()
        self.client.force_authenticate(self.customer)
        first = self.client.post("/api/v1/orders/checkout/", payload, format="json")
        second = self.client.post("/api/v1/orders/checkout/", payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["order_number"], second.data["order_number"])
        self.assertEqual(Order.objects.count(), 1)

    def test_public_product_does_not_expose_cost_price(self):
        self.product.cost_price = "500.00"
        self.product.save(update_fields=["cost_price", "updated_at"])
        response = self.client.get(f"/api/v1/products/catalog/{self.product.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("cost_price", response.data)

    def test_admin_can_upload_product_image(self):
        self.client.force_authenticate(self.admin)
        image_bytes = BytesIO()
        Image.new("RGB", (16, 16), (30, 90, 170)).save(image_bytes, format="PNG")
        image = SimpleUploadedFile(
            "radio.png",
            image_bytes.getvalue(),
            content_type="image/png",
        )
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    "/api/v1/products/upload-image/",
                    {"image": image},
                    format="multipart",
                )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["image_url"].startswith("/media/products/"))

    def test_admin_can_manage_multiple_product_images_with_one_primary(self):
        self.client.force_authenticate(self.admin)
        product_url = f"/api/v1/products/catalog/{self.product.slug}/"
        images = [
            {
                "image_url": "/media/products/front.webp",
                "alt_text": "Front view",
                "is_primary": False,
                "sort_order": 0,
            },
            {
                "image_url": "/media/products/rear.webp",
                "alt_text": "Rear view",
                "is_primary": False,
                "sort_order": 1,
            },
        ]

        response = self.client.patch(product_url, {"images": images}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        saved_images = list(ProductImage.objects.filter(product=self.product))
        self.assertEqual(len(saved_images), 2)
        self.assertTrue(saved_images[0].is_primary)
        self.assertFalse(saved_images[1].is_primary)

        images[0]["is_primary"] = True
        images[1]["is_primary"] = True
        invalid = self.client.patch(product_url, {"images": images}, format="json")

        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("images", invalid.data)

    def test_customer_can_register(self):
        response = self.client.post(
            "/api/v1/users/auth/register/",
            {
                "email": "new@example.com",
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
                "first_name": "New",
                "last_name": "Customer",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "new@example.com")
        self.assertNotIn("access", response.data)

    def test_admin_can_create_order(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(
        POWER_AUTOMATE_ENABLED=True,
        QUOTE_NOTIFICATION_EMAIL="sales@example.com",
    )
    @patch("core.notifications.send_power_automate_event", return_value=True)
    def test_public_quote_submission_remains_available(self, event_sender):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/v1/quotes/", self.quote_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(QuoteRequest.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(response.data["status"], QuoteRequest.Status.NEW)
        self.assertEqual(response.data["order_number"], "")
        self.assertIn("image_url", response.data["items"][0])
        self.assertEqual(len(mail.outbox), 2)
        self.assertCountEqual(
            [message.to[0] for message in mail.outbox],
            ["customer@example.com", "sales@example.com"],
        )
        staff_message = next(
            message for message in mail.outbox if message.to == ["sales@example.com"]
        )
        self.assertIn(
            f"/admin/quotes?quote={QuoteRequest.objects.get().quote_number}",
            staff_message.body,
        )
        self.assertEqual(staff_message.reply_to, ["customer@example.com"])
        customer_message = next(
            message for message in mail.outbox if message.to == ["customer@example.com"]
        )
        self.assertIn("/auth/claim-quote?quote=", customer_message.body)
        self.assertIn("sign in or create an account", customer_message.body)
        event_sender.assert_called_once()
        event_name, event_data = event_sender.call_args.args
        self.assertEqual(event_name, "quote.created")
        self.assertEqual(event_data["quote_number"], QuoteRequest.objects.get().quote_number)
        self.assertNotIn("order_number", event_data)
        self.assertEqual(event_data["items"][0]["sku"], self.product.sku)

    def test_quote_creates_one_order_only_after_agreement_and_invoice(self):
        created = self.client.post("/api/v1/quotes/", self.quote_payload(), format="json")
        quote_url = f"/api/v1/quotes/{created.data['quote_number']}/"
        self.assertEqual(Order.objects.count(), 0)

        self.client.force_authenticate(self.admin)
        premature = self.client.patch(quote_url, {"status": "approved"}, format="json")
        self.assertEqual(premature.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

        reviewing = self.client.patch(quote_url, {"status": "reviewing"}, format="json")
        self.assertEqual(reviewing.status_code, status.HTTP_200_OK)
        self.assertEqual(reviewing.data["quote_number"], created.data["quote_number"])
        self.assertEqual(reviewing.data["status"], QuoteRequest.Status.REVIEWING)
        self.assertEqual(len(reviewing.data["items"]), 1)
        self.assertEqual(reviewing.data["items"][0]["sku"], self.product.sku)
        quote = QuoteRequest.objects.get()
        invoice_payload = {
            "items": [{"id": quote.items.get().id, "quoted_unit_price": "900.00"}],
            "quoted_shipping": "50.00",
            "admin_message": "Valid while stock lasts.",
        }
        self.client.force_authenticate(self.customer)
        claim_response = self.client.post(
            f"{quote_url}claim/",
            {"token": make_guest_quote_claim_token(quote)},
            format="json",
        )
        self.assertEqual(claim_response.status_code, status.HTTP_200_OK)
        hidden_draft = self.client.get(quote_url)
        self.assertEqual(hidden_draft.status_code, status.HTTP_200_OK)
        self.assertIsNone(hidden_draft.data["quoted_total"])
        self.assertIsNone(hidden_draft.data["items"][0]["quoted_unit_price"])

        self.client.force_authenticate(self.customer)
        customer_invoice = self.client.post(
            f"{quote_url}invoice/", invoice_payload, format="json"
        )
        self.assertEqual(customer_invoice.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        self.product.inventory_quantity = 0
        self.product.save(update_fields=["inventory_quantity", "updated_at"])
        with tempfile.TemporaryDirectory() as media_root, override_settings(PRIVATE_MEDIA_ROOT=media_root):
            with self.captureOnCommitCallbacks(execute=True):
                invoiced = self.client.post(
                    f"{quote_url}invoice/", invoice_payload, format="json"
                )
            self.assertEqual(invoiced.status_code, status.HTTP_200_OK)
            self.assertEqual(invoiced.data["status"], QuoteRequest.Status.QUOTED)
            self.assertTrue(invoiced.data["invoice_number"].startswith("INV-"))
            invoice_download_url = f"{quote_url}invoice-pdf/"
            self.assertTrue(invoiced.data["invoice_pdf_url"].endswith(invoice_download_url))
            quote.refresh_from_db()
            self.assertTrue(
                Path(quote.invoice_pdf.path).resolve().is_relative_to(Path(media_root).resolve())
            )
            with quote.invoice_pdf.open("rb") as invoice_file:
                self.assertEqual(invoice_file.read(4), b"%PDF")
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].attachments[0][2], "application/pdf")

            admin_download = self.client.get(invoice_download_url)
            self.assertEqual(admin_download.status_code, status.HTTP_200_OK)
            self.assertEqual(admin_download["Content-Type"], "application/pdf")
            self.assertEqual(admin_download["Cache-Control"], "private, no-store")
            self.assertEqual(b"".join(admin_download.streaming_content)[:4], b"%PDF")

            self.client.force_authenticate(self.customer)
            customer_download = self.client.get(invoice_download_url)
            self.assertEqual(customer_download.status_code, status.HTTP_200_OK)
            customer_download.close()

            outsider = get_user_model().objects.create_user(
                username="invoice-outsider",
                email="invoice-outsider@example.com",
                password="StrongPass123!",
            )
            self.client.force_authenticate(outsider)
            outsider_download = self.client.get(invoice_download_url)
            self.assertEqual(outsider_download.status_code, status.HTTP_404_NOT_FOUND)

            order_number = invoiced.data["order_number"]
            self.client.force_authenticate(self.customer)
            revision_message = self.client.post(
                f"{quote_url}messages/",
                {"body": "Please reduce the price and resend the invoice."},
                format="json",
            )
            self.assertEqual(revision_message.status_code, status.HTTP_200_OK)

            revised_payload = {
                **invoice_payload,
                "items": [{"id": quote.items.get().id, "quoted_unit_price": "850.00"}],
                "quoted_shipping": "25.00",
                "admin_message": "Revised final pricing.",
            }
            self.client.force_authenticate(self.admin)
            with self.captureOnCommitCallbacks(execute=True):
                revised = self.client.post(
                    f"{quote_url}invoice/", revised_payload, format="json"
                )
            self.assertEqual(revised.status_code, status.HTTP_200_OK)
            self.assertEqual(revised.data["quoted_total"], Decimal("875.00"))
            self.assertEqual(revised.data["order_number"], order_number)
            self.assertEqual(Order.objects.count(), 1)

        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.source, Order.Source.QUOTE)
        self.assertEqual(order.total, Decimal("875.00"))
        self.assertEqual(order.quote_request.quote_number, created.data["quote_number"])
        self.assertEqual(invoiced.data["order_number"], order.order_number)

        self.client.force_authenticate(self.admin)
        close_after_approval = self.client.patch(
            quote_url, {"status": "cancelled"}, format="json"
        )
        self.assertEqual(close_after_approval.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 1)

    @override_settings(
        NOTIFICATIONS_ASYNC=True,
        QUOTE_NOTIFICATION_EMAIL="sales@example.com",
        FRONTEND_URL="http://localhost:5173",
    )
    def test_quote_messages_notify_the_other_party_with_portal_links(self):
        self.client.force_authenticate(self.customer)
        created = self.client.post(
            "/api/v1/quotes/", self.quote_payload(), format="json"
        )
        quote_url = f"/api/v1/quotes/{created.data['quote_number']}/"

        self.client.force_authenticate(self.admin)
        reviewing = self.client.patch(
            quote_url, {"status": "reviewing"}, format="json"
        )
        self.assertEqual(reviewing.status_code, status.HTTP_200_OK)

        with self.captureOnCommitCallbacks(execute=True):
            admin_message = self.client.post(
                f"{quote_url}messages/",
                {"body": "Delivery is estimated at two weeks."},
                format="json",
            )
        self.assertEqual(admin_message.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.customer)
        with self.captureOnCommitCallbacks(execute=True):
            customer_message = self.client.post(
                f"{quote_url}messages/",
                {"body": "That delivery schedule works."},
                format="json",
            )
        self.assertEqual(customer_message.status_code, status.HTTP_200_OK)

        customer_notification = UserNotification.objects.get(recipient=self.customer)
        self.assertFalse(customer_notification.is_read)
        self.assertEqual(
            customer_notification.url,
            f"/account?tab=quotes&quote={created.data['quote_number']}",
        )
        customer_inbox = self.client.get("/api/v1/core/notifications/")
        self.assertEqual(customer_inbox.status_code, status.HTTP_200_OK)
        self.assertEqual(customer_inbox.data["unread_count"], 1)
        self.assertEqual(
            customer_inbox.data["notifications"][0]["id"],
            customer_notification.id,
        )

        admin_notification = UserNotification.objects.get(recipient=self.admin)
        self.assertFalse(admin_notification.is_read)
        self.assertEqual(
            admin_notification.url,
            f"/admin/quotes?quote={created.data['quote_number']}",
        )

        cannot_read_admin_notification = self.client.patch(
            f"/api/v1/core/notifications/{admin_notification.id}/read/",
            format="json",
        )
        self.assertEqual(
            cannot_read_admin_notification.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.client.force_authenticate(self.admin)
        inbox = self.client.get("/api/v1/core/notifications/")
        self.assertEqual(inbox.status_code, status.HTTP_200_OK)
        self.assertEqual(inbox.data["unread_count"], 1)
        self.assertEqual(inbox.data["notifications"][0]["id"], admin_notification.id)
        read = self.client.patch(
            f"/api/v1/core/notifications/{admin_notification.id}/read/",
            format="json",
        )
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        self.assertTrue(read.data["is_read"])

        jobs = NotificationJob.objects.filter(
            kind=NotificationJob.Kind.QUOTE_MESSAGE_EMAIL
        )
        self.assertEqual(jobs.count(), 2)
        self.assertEqual(len(mail.outbox), 0)

        call_command("process_notifications", once=True)

        self.assertFalse(jobs.exclude(status=NotificationJob.Status.SENT).exists())
        self.assertEqual(len(mail.outbox), 2)
        customer_email = next(
            message for message in mail.outbox if message.to == ["customer@example.com"]
        )
        staff_email = next(
            message for message in mail.outbox if message.to == ["sales@example.com"]
        )
        quote_number = created.data["quote_number"]
        self.assertIn(
            f"/account?tab=quotes&quote={quote_number}", customer_email.body
        )
        self.assertIn(
            f"/admin/quotes?quote={quote_number}", staff_email.body
        )
        self.assertNotIn("Delivery is estimated", customer_email.body)
        self.assertNotIn("That delivery schedule", staff_email.body)

    def test_customer_can_cancel_own_quote_during_negotiation(self):
        self.client.force_authenticate(self.customer)
        created = self.client.post("/api/v1/quotes/", self.quote_payload(), format="json")
        quote_url = f"/api/v1/quotes/{created.data['quote_number']}/"

        self.client.force_authenticate(self.admin)
        reviewing = self.client.patch(quote_url, {"status": "reviewing"}, format="json")
        self.assertEqual(reviewing.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.customer)
        cancelled = self.client.post(f"{quote_url}cancel/", format="json")
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(cancelled.data["status"], QuoteRequest.Status.CANCELLED)
        self.assertEqual(Order.objects.count(), 0)

        customer_quotes = self.client.get("/api/v1/quotes/")
        self.assertEqual(customer_quotes.status_code, status.HTTP_200_OK)
        self.assertEqual(customer_quotes.data["count"], 0)
        customer_cancelled_quotes = self.client.get(
            "/api/v1/quotes/?display_status=cancelled"
        )
        self.assertEqual(customer_cancelled_quotes.data["count"], 0)

        self.client.force_authenticate(self.admin)
        admin_quotes = self.client.get("/api/v1/quotes/")
        self.assertEqual(admin_quotes.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_quotes.data["count"], 0)
        admin_cancelled_quotes = self.client.get(
            "/api/v1/quotes/?status=cancelled"
        )
        self.assertEqual(admin_cancelled_quotes.data["count"], 0)

    def test_public_quote_rejects_arbitrary_or_hidden_products(self):
        arbitrary_payload = self.quote_payload()
        arbitrary_payload["items"] = [{"product_name": "Invented product", "quantity": 1}]
        arbitrary_response = self.client.post(
            "/api/v1/quotes/", arbitrary_payload, format="json"
        )
        self.assertEqual(arbitrary_response.status_code, status.HTTP_400_BAD_REQUEST)

        self.product.status = Product.Status.DRAFT
        self.product.save(update_fields=["status", "updated_at"])
        hidden_response = self.client.post(
            "/api/v1/quotes/", self.quote_payload(), format="json"
        )
        self.assertEqual(hidden_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(QuoteRequest.objects.count(), 0)

    def test_product_lookup_by_id_does_not_depend_on_catalog_page(self):
        response = self.client.get(f"/api/v1/products/catalog/by-id/{self.product.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.product.id)

    def test_public_category_count_excludes_hidden_products(self):
        Product.objects.create(
            category=self.product.category,
            name="Draft Rack",
            sku="DRAFT-1",
            price="10.00",
            status=Product.Status.DRAFT,
        )
        response = self.client.get("/api/v1/products/categories/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["product_count"], 1)

    def test_admin_login_uses_http_only_refresh_cookie(self):
        login = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": self.admin.email, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_202_ACCEPTED)
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        login = self.client.post(
            "/api/v1/users/auth/staff-mfa/",
            {"challenge": login.data["challenge"], "code": code},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertNotIn("refresh", login.data)
        refresh_cookie = login.cookies[settings.AUTH_REFRESH_COOKIE_NAME]
        self.assertTrue(refresh_cookie["httponly"])

        refreshed = self.client.post("/api/v1/users/auth/refresh/", {}, format="json")
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertIn("access", refreshed.data)
        self.assertNotIn("refresh", refreshed.data)

    def test_order_status_deducts_and_cancel_restores_stock(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        order_url = f"/api/v1/orders/{created.data['order_number']}/"

        with self.captureOnCommitCallbacks(execute=True):
            processing = self.client.patch(order_url, {"status": "processing"}, format="json")
        self.assertEqual(processing.status_code, status.HTTP_200_OK)
        self.assertIn("updated_at", processing.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 4)
        self.assertTrue(Order.objects.get(pk=created.data["id"]).stock_deducted)

        with self.captureOnCommitCallbacks(execute=True):
            cancelled = self.client.patch(order_url, {"status": "cancelled"}, format="json")
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 5)
        self.assertFalse(Order.objects.get(pk=created.data["id"]).stock_deducted)

        admin_orders = self.client.get("/api/v1/orders/")
        self.assertEqual(admin_orders.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_orders.data["count"], 0)
        admin_cancelled_orders = self.client.get(
            "/api/v1/orders/?display_status=cancelled"
        )
        self.assertEqual(admin_cancelled_orders.data["count"], 0)

        self.client.force_authenticate(self.customer)
        customer_orders = self.client.get("/api/v1/orders/")
        self.assertEqual(customer_orders.status_code, status.HTTP_200_OK)
        self.assertEqual(customer_orders.data["count"], 0)
        customer_cancelled_orders = self.client.get(
            "/api/v1/orders/?status=cancelled"
        )
        self.assertEqual(customer_cancelled_orders.data["count"], 0)

    def test_order_and_quote_status_changes_create_portal_notifications(self):
        self.client.force_authenticate(self.admin)
        created_order = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        order_url = f"/api/v1/orders/{created_order.data['order_number']}/"

        with self.captureOnCommitCallbacks(execute=True):
            updated_order = self.client.patch(order_url, {"status": "processing"}, format="json")

        self.assertEqual(updated_order.status_code, status.HTTP_200_OK)
        order_notification = UserNotification.objects.get(
            recipient=self.customer,
            url="/account?tab=orders",
        )
        self.assertIn(created_order.data["order_number"], order_notification.title)
        self.assertIn("Processing", order_notification.message)

        self.client.force_authenticate(self.customer)
        created_quote = self.client.post("/api/v1/quotes/", self.quote_payload(), format="json")
        quote_url = f"/api/v1/quotes/{created_quote.data['quote_number']}/"

        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            updated_quote = self.client.patch(quote_url, {"status": "reviewing"}, format="json")

        self.assertEqual(updated_quote.status_code, status.HTTP_200_OK)
        quote_notification = UserNotification.objects.get(
            recipient=self.customer,
            url=f"/account?tab=quotes&quote={created_quote.data['quote_number']}",
        )
        self.assertIn(created_quote.data["quote_number"], quote_notification.title)
        self.assertIn("Processing", quote_notification.message)

    def test_completed_order_is_terminal(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        order_url = f"/api/v1/orders/{created.data['order_number']}/"
        with self.captureOnCommitCallbacks(execute=True):
            completed = self.client.patch(order_url, {"status": "completed"}, format="json")
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        rejected = self.client.patch(order_url, {"status": "cancelled"}, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paid_order_cannot_be_cancelled(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        order = Order.objects.get(pk=created.data["id"])
        provider, _ = PaymentProvider.objects.get_or_create(
            code=PaymentProvider.Code.STRIPE,
            defaults={"display_name": "Stripe"},
        )
        PaymentAttempt.objects.create(
            order=order,
            provider=provider,
            amount=order.total,
            status=PaymentAttempt.Status.SUCCEEDED,
        )

        detail = self.client.get(f"/api/v1/orders/{order.order_number}/")
        self.assertTrue(detail.data["is_paid"])
        rejected = self.client.patch(
            f"/api/v1/orders/{order.order_number}/",
            {"status": "cancelled"},
            format="json",
        )

        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(rejected.data["status"], "Paid orders cannot be cancelled.")

    @override_settings(
        NOTIFICATIONS_ASYNC=True,
        POWER_AUTOMATE_ENABLED=False,
        QUOTE_NOTIFICATION_EMAIL="sales@example.com",
    )
    def test_quote_notifications_can_be_queued_and_processed(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/v1/quotes/", self.quote_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(NotificationJob.objects.count(), 2)
        self.assertFalse(
            NotificationJob.objects.exclude(status=NotificationJob.Status.PENDING).exists()
        )

        call_command("process_notifications", once=True)
        self.assertFalse(
            NotificationJob.objects.exclude(status=NotificationJob.Status.SENT).exists()
        )
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(
        POWER_AUTOMATE_ENABLED=True,
        POWER_AUTOMATE_WEBHOOK_URL="https://example.invalid/power-automate-trigger",
        POWER_AUTOMATE_TIMEOUT=7,
        POWER_AUTOMATE_SHARED_SECRET="test-secret",
    )
    @patch("common.integrations.power_automate.urlopen")
    def test_power_automate_event_uses_structured_json(self, mocked_urlopen):
        response = MagicMock()
        response.getcode.return_value = 202
        mocked_urlopen.return_value.__enter__.return_value = response

        delivered = send_power_automate_event(
            "quote.created",
            {"quote_number": "QTE-2026-000001", "total": "1000.00"},
        )

        self.assertTrue(delivered)
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["event"], "quote.created")
        self.assertEqual(payload["source"], "rack-and-bracket")
        self.assertEqual(payload["data"]["quote_number"], "QTE-2026-000001")
        self.assertEqual(request.get_header("X-webhook-secret"), "test-secret")
        self.assertEqual(mocked_urlopen.call_args.kwargs["timeout"], 7)

    def test_registered_email_cannot_read_unclaimed_guest_quotes(self):
        QuoteRequest.objects.create(
            requester_company_name="Example Co",
            requester_contact_person="Test Customer",
            requester_email=self.customer.email,
            requester_phone="+1 555 111 2222",
        )
        self.client.force_authenticate(self.customer)
        response = self.client.get("/api/v1/quotes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_guest_quote_claim_link_attaches_quote_and_matching_order(self):
        quote_request = QuoteRequest.objects.create(
            requester_company_name="Example Co",
            requester_contact_person="Test Customer",
            requester_email=self.customer.email,
            requester_phone="+1 555 111 2222",
        )
        order = Order.objects.create(
            user=self.admin,
            quote_request=quote_request,
            source=Order.Source.QUOTE,
            customer_first_name="Test",
            customer_last_name="Customer",
            customer_email=self.customer.email,
            customer_phone="+1 555 111 2222",
            shipping_address="",
            shipping_city="",
            shipping_country="",
        )
        token = make_guest_quote_claim_token(quote_request)

        self.client.force_authenticate(self.customer)
        response = self.client.post(
            f"/api/v1/quotes/{quote_request.quote_number}/claim/",
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        quote_request.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(quote_request.user, self.customer)
        self.assertEqual(order.user, self.customer)
        self.assertEqual(self.client.get("/api/v1/quotes/").data["count"], 1)

    def test_guest_quote_claim_access_returns_the_recipient_email_for_a_valid_link(self):
        quote_request = QuoteRequest.objects.create(
            requester_company_name="Example Co",
            requester_contact_person="Test Customer",
            requester_email=self.customer.email,
            requester_phone="+1 555 111 2222",
        )

        response = self.client.get(
            f"/api/v1/quotes/{quote_request.quote_number}/claim-access/",
            {"token": make_guest_quote_claim_token(quote_request)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["requester_email"], self.customer.email)

    def test_guest_quote_claim_access_returns_the_recipient_email_for_a_valid_link(self):
        quote_request = QuoteRequest.objects.create(
            requester_company_name="Example Co",
            requester_contact_person="Test Customer",
            requester_email=self.customer.email,
            requester_phone="+1 555 111 2222",
        )

        response = self.client.get(
            f"/api/v1/quotes/{quote_request.quote_number}/claim-access/",
            {"token": make_guest_quote_claim_token(quote_request)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["requester_email"], self.customer.email)

    def test_guest_quote_claim_rejects_a_different_account(self):
        User = get_user_model()
        intruder = User.objects.create_user(
            username="intruder@example.com",
            email="intruder@example.com",
            password="StrongPass123!",
        )
        quote_request = QuoteRequest.objects.create(
            requester_company_name="Example Co",
            requester_contact_person="Test Customer",
            requester_email=self.customer.email,
            requester_phone="+1 555 111 2222",
        )

        self.client.force_authenticate(intruder)
        response = self.client.post(
            f"/api/v1/quotes/{quote_request.quote_number}/claim/",
            {"token": make_guest_quote_claim_token(quote_request)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        quote_request.refresh_from_db()
        self.assertIsNone(quote_request.user)

    @patch("quotes.claims.signing.loads", side_effect=signing.SignatureExpired("expired"))
    def test_guest_quote_claim_rejects_an_expired_link(self, _loads):
        quote_request = QuoteRequest.objects.create(
            requester_company_name="Example Co",
            requester_contact_person="Test Customer",
            requester_email=self.customer.email,
            requester_phone="+1 555 111 2222",
        )
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            f"/api/v1/quotes/{quote_request.quote_number}/claim/",
            {"token": "expired"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_signed_in_customer_quote_is_available_without_a_claim_link(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/v1/quotes/", self.quote_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        quote_request = QuoteRequest.objects.get(quote_number=response.data["quote_number"])
        self.assertEqual(quote_request.user, self.customer)
        self.assertEqual(self.client.get("/api/v1/quotes/").data["count"], 1)

    def test_staff_can_update_structured_homepage_content(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            "/api/v1/core/site-settings/admin/",
            {
                "homepage_solution_title": "Connected teams everywhere",
                "homepage_hero_stats": [
                    {"value": "8", "label": "radio models"},
                    {"value": "24/7", "label": "team support"},
                    {"value": "4G", "label": "nationwide coverage"},
                ],
                "homepage_resources": [
                    {
                        "eyebrow": "GUIDE",
                        "title": "Radio guide",
                        "description": "Choose the right radio.",
                        "image_url": "/images/article-guide.png",
                        "url": "/guides/radios",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["homepage_solution_title"], "Connected teams everywhere")
        self.assertEqual(response.data["homepage_hero_stats"][1]["value"], "24/7")
        self.assertEqual(response.data["homepage_resources"][0]["url"], "/guides/radios")

    def test_product_search_covers_catalog_fields(self):
        for term in ("42U Rack", "SR-42", "Server Racks", "1000", "Height", "42U"):
            response = self.client.get("/api/v1/products/catalog/", {"search": term})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 1, term)

    def test_price_range_uses_sale_price(self):
        self.product.sale_price = "750.00"
        self.product.save(update_fields=["sale_price", "updated_at"])
        response = self.client.get(
            "/api/v1/products/catalog/",
            {"min_price": "700", "max_price": "800"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_catalog_stock_filter_supports_server_pagination(self):
        Product.objects.create(
            category=self.product.category,
            name="Out of stock rack",
            sku="OUT-1",
            price="500.00",
            inventory_quantity=0,
            status=Product.Status.PUBLISHED,
        )

        response = self.client.get(
            "/api/v1/products/catalog/",
            {"stock": "true", "page": 1, "page_size": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sku"], self.product.sku)

    def test_catalog_orders_by_effective_sale_price(self):
        Product.objects.create(
            category=self.product.category,
            name="Discounted rack",
            sku="SALE-1",
            price="1200.00",
            sale_price="400.00",
            inventory_quantity=1,
            status=Product.Status.PUBLISHED,
        )

        response = self.client.get(
            "/api/v1/products/catalog/",
            {"ordering": "current_price_value", "page_size": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["sku"], "SALE-1")

    def test_admin_can_search_order_by_internal_id(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        response = self.client.get("/api/v1/orders/", {"search": str(created.data["id"])})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], created.data["id"])

    def test_promotions_are_admin_managed_and_validate_percentage(self):
        payload = {
            "code": "FIELD10",
            "title": "Field team discount",
            "discount_type": "percentage",
            "discount_value": "10.00",
            "is_active": True,
        }
        self.client.force_authenticate(self.customer)
        denied = self.client.post("/api/v1/core/promotions/", payload, format="json")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        created = self.client.post("/api/v1/core/promotions/", payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["status"], "active")
        self.assertTrue(Promotion.objects.filter(code="FIELD10").exists())

        invalid = self.client.post(
            "/api/v1/core/promotions/",
            {**payload, "code": "TOO-MUCH", "discount_value": "101.00"},
            format="json",
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refresh_for_deleted_user_expires_cleanly(self):
        response = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": self.customer.email, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer.delete()
        refreshed = self.client.post("/api/v1/users/auth/refresh/", format="json")
        self.assertEqual(refreshed.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(refreshed.data["detail"], "Refresh session is no longer valid.")
