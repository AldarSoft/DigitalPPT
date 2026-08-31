from unittest.mock import Mock, patch
import logging

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from common.email_delivery import _graph_client, send_application_email
from common.security_logging import JsonFormatter
from core.models import NotificationJob, OperationalRun
from core.models import SiteSetting
from core.operations import operational_status, record_run
from rest_framework.test import APITestCase


class SiteSettingSecurityTests(APITestCase):
    def setUp(self):
        self.settings = SiteSetting.get_solo()
        self.settings.bank_transfer_enabled = True
        self.settings.bank_beneficiary_name = "Digital PTT"
        self.settings.bank_name = "Private Bank"
        self.settings.bank_account_number = "123456789"
        self.settings.bank_iban = "MN00PRIVATE"
        self.settings.save()
        self.staff = get_user_model().objects.create_user(
            username="settings-admin",
            email="settings-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )

    def test_public_settings_do_not_expose_bank_or_commerce_configuration(self):
        response = self.client.get("/api/v1/core/site-settings/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("bank_account_number", response.data)
        self.assertNotIn("bank_iban", response.data)
        self.assertNotIn("commerce_defaults_enabled", response.data)

    def test_admin_settings_require_staff_and_include_private_configuration(self):
        denied = self.client.get("/api/v1/core/site-settings/admin/")
        self.assertEqual(denied.status_code, 401)
        self.client.force_authenticate(self.staff)
        response = self.client.get("/api/v1/core/site-settings/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bank_account_number"], "123456789")


@override_settings(CONTENT_SECURITY_POLICY="default-src 'self'")
class SecurityHeaderTests(APITestCase):
    def test_security_headers_are_added_when_middleware_is_enabled(self):
        from common.security_headers import SecurityHeadersMiddleware

        response = SecurityHeadersMiddleware(lambda request: self.client.get("/health/"))(None)
        self.assertEqual(response["Content-Security-Policy"], "default-src 'self'")
        self.assertIn("camera=()", response["Permissions-Policy"])


class SecurityLoggingTests(SimpleTestCase):
    def test_json_logs_redact_sensitive_values(self):
        record = logging.LogRecord(
            "security.test",
            logging.WARNING,
            __file__,
            1,
            "authorization=BearerToken password=Secret123",
            (),
            None,
        )
        rendered = JsonFormatter().format(record)
        self.assertIn('"logger": "security.test"', rendered)
        self.assertNotIn("BearerToken", rendered)
        self.assertNotIn("Secret123", rendered)


@override_settings(
    MICROSOFT_GRAPH_EMAIL_ENABLED=True,
    MICROSOFT_GRAPH_TENANT_ID="tenant-id",
    MICROSOFT_GRAPH_CLIENT_ID="client-id",
    MICROSOFT_GRAPH_CLIENT_SECRET="client-secret",
    MICROSOFT_GRAPH_SENDER_EMAIL="salesteam@rack-n-brackets.com",
    MICROSOFT_GRAPH_TIMEOUT=30,
)
class MicrosoftGraphEmailTests(SimpleTestCase):
    def setUp(self):
        _graph_client.cache_clear()

    def tearDown(self):
        _graph_client.cache_clear()

    @patch("common.email_delivery.requests.post")
    @patch("common.email_delivery.ConfidentialClientApplication")
    def test_sends_graph_email_with_reply_to(self, client_class, post):
        client = client_class.return_value
        client.acquire_token_for_client.return_value = {"access_token": "token"}
        post.return_value = Mock(status_code=202)

        send_application_email(
            subject="New quote",
            text_body="Quote body",
            html_body="<p>Quote body</p>",
            recipients=["salesteam@rack-n-brackets.com"],
            reply_to=["customer@example.com"],
        )

        request = post.call_args
        self.assertEqual(
            request.args[0],
            "https://graph.microsoft.com/v1.0/users/"
            "salesteam@rack-n-brackets.com/sendMail",
        )
        self.assertEqual(request.kwargs["timeout"], 30)
        message = request.kwargs["json"]["message"]
        self.assertEqual(message["body"]["contentType"], "HTML")
        self.assertEqual(
            message["replyTo"][0]["emailAddress"]["address"],
            "customer@example.com",
        )


class OperationalHealthTests(TestCase):
    def test_record_run_persists_successful_result(self):
        run, details = record_run(
            kind=OperationalRun.Kind.LICENSE_RECONCILIATION,
            operation=lambda: {"processed": 2, "notified": 1},
        )

        self.assertEqual(run.status, OperationalRun.Status.SUCCEEDED)
        self.assertEqual(details["processed"], 2)
        self.assertEqual(run.details["notified"], 1)
        self.assertIsNotNone(run.finished_at)

    @override_settings(
        LICENSE_RECONCILIATION_MAX_AGE_HOURS=26,
        NOTIFICATION_WORKER_MAX_AGE_MINUTES=10,
    )
    def test_operations_check_reports_fresh_runs_and_exhausted_jobs(self):
        now = timezone.now()
        OperationalRun.objects.bulk_create([
            OperationalRun(
                kind=OperationalRun.Kind.LICENSE_RECONCILIATION,
                status=OperationalRun.Status.SUCCEEDED,
                started_at=now,
                finished_at=now,
            ),
            OperationalRun(
                kind=OperationalRun.Kind.NOTIFICATION_DELIVERY,
                status=OperationalRun.Status.SUCCEEDED,
                started_at=now,
                finished_at=now,
            ),
        ])

        self.assertFalse(operational_status()["license_reconciliation"]["is_stale"])
        call_command("check_operations")

        NotificationJob.objects.create(
            kind=NotificationJob.Kind.LICENSE_EXPIRY_EMAIL,
            status=NotificationJob.Status.FAILED,
            attempts=5,
        )
        with self.assertRaises(CommandError):
            call_command("check_operations")


class ProductionSettingsCheckTests(SimpleTestCase):
    @override_settings(
        DEBUG=False,
        SECRET_KEY="s" * 64,
        JWT_SIGNING_KEY="j" * 64,
        DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}},
        ALLOWED_HOSTS=["app.digitalptt.example"],
        CSRF_TRUSTED_ORIGINS=["https://app.digitalptt.example"],
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        NOTIFICATIONS_ASYNC=True,
        PAYMENTS_DEVELOPMENT_SIMULATOR=False,
        REDIS_URL="redis://cache.internal:6379/0",
        CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://cache.internal:6379/0"}},
        CONTENT_SECURITY_POLICY="default-src 'self'",
        PRIVATE_MEDIA_ROOT="/srv/digitalptt/private",
        MEDIA_ROOT="/srv/digitalptt/media",
        STATIC_ROOT="/srv/digitalptt/static",
    )
    def test_production_settings_check_accepts_a_safe_configuration(self):
        call_command("check_production_settings")
