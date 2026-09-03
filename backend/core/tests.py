from unittest.mock import Mock, patch
import logging
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from common.email_delivery import _graph_client, send_application_email
from common.security_logging import JsonFormatter
from core.models import NotificationJob, OperationalRun, RequestThrottleBucket
from core.models import SiteSetting
from core.notifications import _staff_recipients
from core.operations import operational_status, record_run
from rest_framework.test import APITestCase
from users.roles import StaffRole, assign_staff_roles
from common.throttles import DatabaseScopedRateThrottle


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
            is_superuser=True,
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


class StoreLinkValidationTests(APITestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="link-admin",
            email="link-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_authenticate(self.staff)

    def test_banner_rejects_unsafe_schemes(self):
        from core.models import Banner
        from core.serializers import BannerSerializer

        serializer = BannerSerializer(data={
            "title": "Unsafe banner",
            "cta_url": "javascript:alert(1)",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("cta_url", serializer.errors)

        serializer = BannerSerializer(data={
            "title": "Unsafe image",
            "cta_url": "",
            "image_url": "data:text/html;base64,PHNjcmlwdD4=",
        })
        self.assertFalse(serializer.is_valid())

        serializer = BannerSerializer(data={
            "title": "Safe banner",
            "cta_url": "/products",
            "image_url": "https://cdn.example.com/banner.png",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_site_setting_rejects_unsafe_schemes_and_resources(self):
        from core.models import SiteSetting
        from core.serializers import AdminSiteSettingSerializer

        serializer = AdminSiteSettingSerializer(instance=SiteSetting.get_solo(), data={
            "homepage_contact_cta_url": "javascript:alert(1)",
        }, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn("homepage_contact_cta_url", serializer.errors)

        serializer = AdminSiteSettingSerializer(instance=SiteSetting.get_solo(), data={
            "homepage_resources": [
                {"title": "Unsafe", "url": "javascript:alert(1)"},
            ],
        }, partial=True)
        self.assertFalse(serializer.is_valid())

        serializer = AdminSiteSettingSerializer(instance=SiteSetting.get_solo(), data={
            "homepage_hero_secondary_cta_url": "#contact",
            "homepage_contact_cta_url": "https://digitalptt.example/contact",
            "homepage_resources": [
                {"title": "Safe", "url": "/articles/vhf"},
                {"title": "Email", "url": "mailto:sales@digitalptt.example"},
            ],
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_model_clean_rejects_unsafe_links(self):
        from django.core.exceptions import ValidationError
        from core.models import Banner, SiteSetting

        with self.assertRaises(ValidationError):
            Banner(title="Unsafe", cta_url="javascript:alert(1)").full_clean()
        with self.assertRaises(ValidationError):
            SiteSetting(
                homepage_contact_cta_url="data:text/html,hello"
            ).full_clean()
        with self.assertRaises(ValidationError):
            Banner(title="Protocol-relative", cta_url="//attacker.example/path").full_clean()
        with self.assertRaises(ValidationError):
            Banner(title="Insecure HTTP", cta_url="http://example.com/path").full_clean()
        Banner(title="Safe", cta_url="/products").full_clean()


class ApiDocsGatingTests(APITestCase):
    @staticmethod
    def _reload_urls():
        from importlib import reload
        import config.urls
        from django.urls import clear_url_caches

        reload(config.urls)
        clear_url_caches()

    @override_settings(API_DOCS_ENABLED=False)
    def test_schema_and_docs_return_404_when_disabled(self):
        self._reload_urls()
        self.addCleanup(self._reload_urls)
        for path in ("/api/schema/", "/api/docs/", "/api/redoc/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)

    @override_settings(API_DOCS_ENABLED=True)
    def test_schema_and_docs_are_available_when_enabled(self):
        self._reload_urls()
        self.addCleanup(self._reload_urls)
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)


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


class StaffNotificationRecipientTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="notification-superuser@example.com",
            email="notification-superuser@example.com",
            password="StrongPass123!",
        )
        self.support = User.objects.create_user(
            username="notification-support@example.com",
            email="notification-support@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.finance = User.objects.create_user(
            username="notification-finance@example.com",
            email="notification-finance@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.order_manager = User.objects.create_user(
            username="notification-orders@example.com",
            email="notification-orders@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        assign_staff_roles(self.support, [StaffRole.SUPPORT])
        assign_staff_roles(self.finance, [StaffRole.FINANCE])
        assign_staff_roles(self.order_manager, [StaffRole.INVENTORY_OPERATOR])

    def test_staff_notifications_are_limited_to_relevant_roles(self):
        quote_recipient_ids = set(
            _staff_recipients("manage_quotes", "confirm_bank_payments").values_list(
                "id", flat=True
            )
        )
        order_recipient_ids = set(
            _staff_recipients("manage_orders").values_list("id", flat=True)
        )

        self.assertEqual(quote_recipient_ids, {self.superuser.id, self.finance.id})
        self.assertEqual(order_recipient_ids, {self.superuser.id, self.order_manager.id})


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {
            "database_test": "2/min",
        },
    }
)
class DatabaseThrottleTests(TestCase):
    class View:
        throttle_scope = "database_test"

    def setUp(self):
        self.factory = RequestFactory()

    def test_database_throttle_hashes_identity_and_enforces_the_window(self):
        request = self.factory.get("/throttled", REMOTE_ADDR="203.0.113.42")

        self.assertTrue(DatabaseScopedRateThrottle().allow_request(request, self.View()))
        self.assertTrue(DatabaseScopedRateThrottle().allow_request(request, self.View()))
        denied = DatabaseScopedRateThrottle()
        self.assertFalse(denied.allow_request(request, self.View()))
        self.assertGreater(denied.wait(), 0)

        bucket = RequestThrottleBucket.objects.get(scope="database_test")
        self.assertEqual(bucket.request_count, 2)
        self.assertNotIn("203.0.113.42", bucket.key)

        bucket.expires_at = timezone.now() - timedelta(seconds=1)
        bucket.save(update_fields=["expires_at", "updated_at"])
        self.assertTrue(DatabaseScopedRateThrottle().allow_request(request, self.View()))
        bucket.refresh_from_db()
        self.assertEqual(bucket.request_count, 1)


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
        DJANGO_ADMIN_ENABLED=False,
        API_DOCS_ENABLED=False,
        CONTENT_SECURITY_POLICY="default-src 'self'",
        PRIVATE_MEDIA_ROOT="/srv/digitalptt/private",
        MEDIA_ROOT="/srv/digitalptt/media",
        STATIC_ROOT="/srv/digitalptt/static",
    )
    def test_production_settings_check_accepts_a_safe_configuration(self):
        call_command("check_production_settings")

    @override_settings(DJANGO_ADMIN_ENABLED=True)
    def test_production_settings_check_rejects_django_admin(self):
        with self.assertRaises(CommandError):
            call_command("check_production_settings")

    @override_settings(API_DOCS_ENABLED=True)
    def test_production_settings_check_rejects_public_api_docs(self):
        with self.assertRaises(CommandError):
            call_command("check_production_settings")

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_THROTTLE_CLASSES": [
                "rest_framework.throttling.ScopedRateThrottle",
            ],
        }
    )
    def test_production_settings_check_requires_database_throttling(self):
        with self.assertRaises(CommandError):
            call_command("check_production_settings")
