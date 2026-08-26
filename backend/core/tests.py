from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from common.email_delivery import _graph_client, send_application_email
from core.models import NotificationJob, OperationalRun
from core.operations import operational_status, record_run


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
        SECRET_KEY="test-production-secret",
        DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}},
        ALLOWED_HOSTS=["app.digitalptt.example"],
        CSRF_TRUSTED_ORIGINS=["https://app.digitalptt.example"],
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        NOTIFICATIONS_ASYNC=True,
        PAYMENTS_DEVELOPMENT_SIMULATOR=False,
    )
    def test_production_settings_check_accepts_a_safe_configuration(self):
        call_command("check_production_settings")
