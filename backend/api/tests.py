import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.management import call_command
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Product, ProductSpecification
from quotes.models import QuoteRequest
from orders.models import Order
from common.integrations.power_automate import send_power_automate_event
from core.models import NotificationJob, Promotion


class ActiveApiPermissionTests(APITestCase):
    def setUp(self):
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

    def test_admin_can_request_and_complete_password_reset(self):
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
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("NewStrongPass456!"))

    def test_customer_can_request_password_reset(self):
        response = self.client.post(
            "/api/v1/users/auth/password-reset/",
            {"email": self.customer.email},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_guest_checkout_uses_server_price(self):
        payload = self.order_payload()
        payload["items"][0]["unit_price"] = "0.01"
        response = self.client.post(
            "/api/v1/orders/checkout/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total"], Decimal("1000.00"))
        self.assertEqual(response.data["items"][0]["unit_price"], Decimal("1000.00"))

    def test_public_product_does_not_expose_cost_price(self):
        self.product.cost_price = "500.00"
        self.product.save(update_fields=["cost_price", "updated_at"])
        response = self.client.get(f"/api/v1/products/catalog/{self.product.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("cost_price", response.data)

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
        self.assertEqual(response.data["user"]["email"], "new@example.com")

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
        event_sender.assert_called_once()
        event_name, event_data = event_sender.call_args.args
        self.assertEqual(event_name, "quote.created")
        self.assertEqual(event_data["quote_number"], QuoteRequest.objects.get().quote_number)
        self.assertNotIn("order_number", event_data)
        self.assertEqual(event_data["items"][0]["sku"], self.product.sku)

    def test_quote_creates_one_order_only_after_staff_approval(self):
        created = self.client.post("/api/v1/quotes/", self.quote_payload(), format="json")
        quote_url = f"/api/v1/quotes/{created.data['quote_number']}/"
        self.assertEqual(Order.objects.count(), 0)

        self.client.force_authenticate(self.admin)
        premature = self.client.patch(quote_url, {"status": "approved"}, format="json")
        self.assertEqual(premature.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

        for next_status in ("reviewing", "quoted"):
            response = self.client.patch(quote_url, {"status": next_status}, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(Order.objects.count(), 0)

        approved = self.client.patch(quote_url, {"status": "approved"}, format="json")
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.quote_request.quote_number, created.data["quote_number"])
        self.assertEqual(approved.data["order_number"], order.order_number)

        repeated = self.client.patch(quote_url, {"status": "approved"}, format="json")
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.count(), 1)

        close_after_approval = self.client.patch(
            quote_url, {"status": "closed"}, format="json"
        )
        self.assertEqual(close_after_approval.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 1)

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
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertNotIn("refresh", login.data)
        refresh_cookie = login.cookies["rack_refresh"]
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
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 4)
        self.assertTrue(Order.objects.get(pk=created.data["id"]).stock_deducted)

        with self.captureOnCommitCallbacks(execute=True):
            cancelled = self.client.patch(order_url, {"status": "cancelled"}, format="json")
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 5)
        self.assertFalse(Order.objects.get(pk=created.data["id"]).stock_deducted)

    def test_completed_order_is_terminal(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post("/api/v1/orders/", self.order_payload(), format="json")
        order_url = f"/api/v1/orders/{created.data['order_number']}/"
        with self.captureOnCommitCallbacks(execute=True):
            completed = self.client.patch(order_url, {"status": "completed"}, format="json")
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        rejected = self.client.patch(order_url, {"status": "cancelled"}, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_customer_only_sees_own_email_quotes(self):
        QuoteRequest.objects.create(
            requester_company_name="Other Co",
            requester_contact_person="Other User",
            requester_email="other@example.com",
            requester_phone="+1 555 111 2222",
        )
        self.client.force_authenticate(self.customer)
        response = self.client.get("/api/v1/quotes/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_staff_can_update_structured_homepage_content(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            "/api/v1/core/site-settings/",
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
