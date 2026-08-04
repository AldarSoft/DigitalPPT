from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from common.email_delivery import _graph_client, send_application_email


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
