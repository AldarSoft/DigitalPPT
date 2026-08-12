from __future__ import annotations

import base64
from functools import lru_cache
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ImproperlyConfigured
from msal import ConfidentialClientApplication


class EmailDeliveryError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _graph_client() -> ConfidentialClientApplication:
    required_settings = {
        "MICROSOFT_GRAPH_TENANT_ID": settings.MICROSOFT_GRAPH_TENANT_ID,
        "MICROSOFT_GRAPH_CLIENT_ID": settings.MICROSOFT_GRAPH_CLIENT_ID,
        "MICROSOFT_GRAPH_CLIENT_SECRET": settings.MICROSOFT_GRAPH_CLIENT_SECRET,
        "MICROSOFT_GRAPH_SENDER_EMAIL": settings.MICROSOFT_GRAPH_SENDER_EMAIL,
    }
    missing = [name for name, value in required_settings.items() if not value]
    if missing:
        raise ImproperlyConfigured(
            f"Microsoft Graph email is missing settings: {', '.join(missing)}"
        )

    return ConfidentialClientApplication(
        settings.MICROSOFT_GRAPH_CLIENT_ID,
        authority=(
            "https://login.microsoftonline.com/"
            f"{settings.MICROSOFT_GRAPH_TENANT_ID}"
        ),
        client_credential=settings.MICROSOFT_GRAPH_CLIENT_SECRET,
    )


def _graph_access_token() -> str:
    result = _graph_client().acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    access_token = result.get("access_token")
    if not access_token:
        error_code = result.get("error", "token_error")
        correlation_id = result.get("correlation_id", "unknown")
        raise EmailDeliveryError(
            f"Microsoft Graph token failed ({error_code}, correlation {correlation_id})."
        )
    return access_token


def _send_with_graph(
    *,
    subject: str,
    text_body: str,
    recipients: list[str],
    html_body: str | None,
    reply_to: list[str],
    attachments: list[tuple[str, bytes, str]],
) -> None:
    content = html_body or text_body
    message = {
        "subject": subject,
        "body": {
            "contentType": "HTML" if html_body else "Text",
            "content": content,
        },
        "toRecipients": [
            {"emailAddress": {"address": address}} for address in recipients
        ],
    }
    if reply_to:
        message["replyTo"] = [
            {"emailAddress": {"address": address}} for address in reply_to
        ]
    if attachments:
        message["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": content_type,
                "contentBytes": base64.b64encode(content).decode("ascii"),
            }
            for filename, content, content_type in attachments
        ]

    sender = quote(settings.MICROSOFT_GRAPH_SENDER_EMAIL, safe="@._-")
    response = requests.post(
        f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
        headers={
            "Authorization": f"Bearer {_graph_access_token()}",
            "Content-Type": "application/json",
        },
        json={"message": message, "saveToSentItems": True},
        timeout=settings.MICROSOFT_GRAPH_TIMEOUT,
    )
    if response.status_code != 202:
        raise EmailDeliveryError(
            f"Microsoft Graph sendMail returned HTTP {response.status_code}."
        )


def send_application_email(
    *,
    subject: str,
    text_body: str,
    recipients: list[str],
    html_body: str | None = None,
    reply_to: list[str] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    reply_to = reply_to or []
    attachments = attachments or []
    if settings.MICROSOFT_GRAPH_EMAIL_ENABLED:
        _send_with_graph(
            subject=subject,
            text_body=text_body,
            recipients=recipients,
            html_body=html_body,
            reply_to=reply_to,
            attachments=attachments,
        )
        return

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        reply_to=reply_to,
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    for filename, content, content_type in attachments:
        message.attach(filename, content, content_type)
    message.send(fail_silently=False)
