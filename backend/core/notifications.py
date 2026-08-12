from __future__ import annotations

import logging
from html import escape
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from common.email_delivery import send_application_email
from common.integrations.power_automate import send_power_automate_event
from core.models import NotificationJob

logger = logging.getLogger(__name__)


def _quote_context(payload: dict):
    from quotes.models import QuoteRequest

    quote = QuoteRequest.objects.prefetch_related("items").get(pk=payload["quote_id"])
    return quote


def _quote_event_data(quote) -> dict:
    return {
        "quote_number": quote.quote_number,
        "quote_status": quote.status,
        "company": quote.requester_company_name,
        "contact_person": quote.requester_contact_person,
        "email": quote.requester_email,
        "phone": quote.requester_phone,
        "notes": quote.notes,
        "created_at": quote.created_at.isoformat(),
        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "sku": item.sku,
                "quantity": item.quantity,
                "specifications": item.specifications,
            }
            for item in quote.items.all()
        ],
    }


def _quote_items_text(quote) -> str:
    return "\n".join(
        f"- {item.product_name} ({item.sku or 'No SKU'}) x {item.quantity}"
        for item in quote.items.all()
    )


def _quote_items_html(quote) -> str:
    items = "".join(
        "<li>"
        f"{escape(item.product_name)} "
        f"({escape(item.sku or 'No SKU')}) &times; {item.quantity}"
        "</li>"
        for item in quote.items.all()
    )
    return f"<ul>{items}</ul>"


def _admin_quote_url(quote_request) -> str:
    base_url = settings.FRONTEND_URL.rstrip("/")
    quote_number = quote(quote_request.quote_number, safe="")
    return f"{base_url}/admin/quotes?quote={quote_number}"


def _customer_quote_url(quote_request) -> str:
    base_url = settings.FRONTEND_URL.rstrip("/")
    quote_number = quote(quote_request.quote_number, safe="")
    return f"{base_url}/account?tab=quotes&quote={quote_number}"


def _send_quote_customer_email(payload: dict) -> None:
    quote = _quote_context(payload)
    text_body = (
        f"Hello {quote.requester_contact_person},\n\n"
        f"We received your quote request {quote.quote_number}.\n"
        "No order has been created yet.\n\n"
        "Requested products:\n"
        f"{_quote_items_text(quote)}\n\n"
        "Our sales team will contact you with confirmed pricing and delivery details.\n\n"
        f"{settings.SITE_NAME}"
    )
    html_body = (
        f"<p>Hello {escape(quote.requester_contact_person)},</p>"
        f"<p>We received your quote request <strong>{escape(quote.quote_number)}</strong>. "
        "No order has been created yet.</p>"
        "<p><strong>Requested products</strong></p>"
        f"{_quote_items_html(quote)}"
        "<p>Our sales team will contact you with confirmed pricing and delivery details.</p>"
        f"<p>{escape(settings.SITE_NAME)}</p>"
    )
    send_application_email(
        subject=f"Quote received: {quote.quote_number}",
        text_body=text_body,
        html_body=html_body,
        recipients=[quote.requester_email],
    )


def _send_quote_staff_email(payload: dict) -> None:
    quote = _quote_context(payload)
    admin_url = _admin_quote_url(quote)
    text_body = (
        f"Quote: {quote.quote_number}\n"
        f"Company: {quote.requester_company_name or '-'}\n"
        f"Contact: {quote.requester_contact_person}\n"
        f"Email: {quote.requester_email}\n"
        f"Phone: {quote.requester_phone or '-'}\n\n"
        "Requested products:\n"
        f"{_quote_items_text(quote)}\n\n"
        f"Review quote: {admin_url}"
    )
    html_body = (
        f"<h2>New quote request: {escape(quote.quote_number)}</h2>"
        f"<p><strong>Company:</strong> {escape(quote.requester_company_name or '-')}<br>"
        f"<strong>Contact:</strong> {escape(quote.requester_contact_person)}<br>"
        f"<strong>Email:</strong> {escape(quote.requester_email)}<br>"
        f"<strong>Phone:</strong> {escape(quote.requester_phone or '-')}</p>"
        "<p><strong>Requested products</strong></p>"
        f"{_quote_items_html(quote)}"
        f'<p><a href="{escape(admin_url, quote=True)}">Open quote in admin</a></p>'
    )
    send_application_email(
        subject=f"New quote request: {quote.quote_number}",
        text_body=text_body,
        html_body=html_body,
        recipients=[settings.QUOTE_NOTIFICATION_EMAIL],
        reply_to=[quote.requester_email],
    )


def _send_quote_webhook(payload: dict) -> None:
    quote = _quote_context(payload)
    if not send_power_automate_event("quote.created", _quote_event_data(quote)):
        raise RuntimeError("Power Automate did not accept the quote event.")


def _send_quote_ready_email(payload: dict) -> None:
    quote_request = _quote_context(payload)
    account_url = f"{settings.FRONTEND_URL.rstrip('/')}/account?tab=quotes"
    priced_items = "\n".join(
        f"- {item.product_name} x {item.quantity}: {item.quoted_line_total}"
        for item in quote_request.items.all()
    )
    text_body = (
        f"Hello {quote_request.requester_contact_person},\n\n"
        f"Invoice {quote_request.invoice_number} for quote {quote_request.quote_number} is ready.\n\n"
        f"{priced_items}\n"
        f"Shipping: {quote_request.quoted_shipping}\n"
        f"Total: {quote_request.quoted_total}\n\n"
        f"Download and pay the invoice in your account: {account_url}\n\n"
        f"{settings.SITE_NAME}"
    )
    html_items = "".join(
        f"<li>{escape(item.product_name)} &times; {item.quantity}: {item.quoted_line_total}</li>"
        for item in quote_request.items.all()
    )
    html_body = (
        f"<p>Hello {escape(quote_request.requester_contact_person)},</p>"
        f"<p>Invoice <strong>{escape(quote_request.invoice_number or '')}</strong> for quote "
        f"<strong>{escape(quote_request.quote_number)}</strong> is ready.</p>"
        f"<ul>{html_items}</ul>"
        f"<p><strong>Shipping:</strong> {quote_request.quoted_shipping}<br>"
        f"<strong>Total:</strong> {quote_request.quoted_total}</p>"
        f'<p><a href="{escape(account_url, quote=True)}">Download and pay invoice</a></p>'
        f"<p>{escape(settings.SITE_NAME)}</p>"
    )
    attachments = []
    if quote_request.invoice_pdf:
        with quote_request.invoice_pdf.open("rb") as invoice_file:
            attachments.append((
                f"{quote_request.invoice_number}.pdf",
                invoice_file.read(),
                "application/pdf",
            ))
    send_application_email(
        subject=f"Invoice ready: {quote_request.invoice_number}",
        text_body=text_body,
        html_body=html_body,
        recipients=[quote_request.requester_email],
        attachments=attachments,
    )


def _send_quote_message_email(payload: dict) -> None:
    from quotes.models import QuoteMessage

    message = QuoteMessage.objects.select_related("quote_request", "author").get(
        pk=payload["message_id"]
    )
    quote_request = message.quote_request
    sender_name = (
        message.author.get_full_name().strip()
        or message.author.email
        if message.author
        else message.get_sender_role_display()
    )

    if message.sender_role == QuoteMessage.SenderRole.ADMIN:
        recipients = [quote_request.requester_email]
        recipient_name = quote_request.requester_contact_person
        portal_url = _customer_quote_url(quote_request)
    else:
        if not settings.QUOTE_NOTIFICATION_EMAIL:
            return
        recipients = [settings.QUOTE_NOTIFICATION_EMAIL]
        recipient_name = "Sales team"
        portal_url = _admin_quote_url(quote_request)

    text_body = (
        f"Hello {recipient_name},\n\n"
        f"{sender_name} sent a new message about quote {quote_request.quote_number}.\n"
        "Open the quote to read and reply in the negotiation history:\n"
        f"{portal_url}\n\n"
        "This email is a notification. Keep quote replies inside the portal so the "
        "complete conversation stays with the quote.\n\n"
        f"{settings.SITE_NAME}"
    )
    html_body = (
        f"<p>Hello {escape(recipient_name)},</p>"
        f"<p><strong>{escape(sender_name)}</strong> sent a new message about quote "
        f"<strong>{escape(quote_request.quote_number)}</strong>.</p>"
        f'<p><a href="{escape(portal_url, quote=True)}">Open quote conversation</a></p>'
        "<p>This email is a notification. Keep quote replies inside the portal so "
        "the complete conversation stays with the quote.</p>"
        f"<p>{escape(settings.SITE_NAME)}</p>"
    )
    send_application_email(
        subject=f"New quote message: {quote_request.quote_number}",
        text_body=text_body,
        html_body=html_body,
        recipients=recipients,
    )


def _send_order_status_email(payload: dict) -> None:
    from orders.models import Order

    order = Order.objects.get(pk=payload["order_id"])
    status_label = payload["new_status"].replace("_", " ").title()
    text_body = (
        f"Hello {order.customer_first_name},\n\n"
        f"Your order {order.order_number} is now {status_label}.\n"
        f"Order total: {order.total}\n\n"
        f"{settings.SITE_NAME}"
    )
    html_body = (
        f"<p>Hello {escape(order.customer_first_name)},</p>"
        f"<p>Your order <strong>{escape(order.order_number)}</strong> is now "
        f"<strong>{escape(status_label)}</strong>.</p>"
        f"<p><strong>Order total:</strong> {order.total}</p>"
        f"<p>{escape(settings.SITE_NAME)}</p>"
    )
    send_application_email(
        subject=f"Order update: {order.order_number}",
        text_body=text_body,
        html_body=html_body,
        recipients=[order.customer_email],
    )


def _send_order_status_webhook(payload: dict) -> None:
    from orders.models import Order

    order = Order.objects.get(pk=payload["order_id"])
    if not send_power_automate_event(
        "order.status_changed",
        {
            "order_number": order.order_number,
            "previous_status": payload["previous_status"],
            "status": payload["new_status"],
            "customer_email": order.customer_email,
            "total": str(order.total),
            "updated_at": order.updated_at.isoformat(),
        },
    ):
        raise RuntimeError("Power Automate did not accept the order status event.")


HANDLERS = {
    NotificationJob.Kind.QUOTE_CUSTOMER_EMAIL: _send_quote_customer_email,
    NotificationJob.Kind.QUOTE_STAFF_EMAIL: _send_quote_staff_email,
    NotificationJob.Kind.QUOTE_WEBHOOK: _send_quote_webhook,
    NotificationJob.Kind.QUOTE_READY_EMAIL: _send_quote_ready_email,
    NotificationJob.Kind.QUOTE_MESSAGE_EMAIL: _send_quote_message_email,
    NotificationJob.Kind.ORDER_STATUS_EMAIL: _send_order_status_email,
    NotificationJob.Kind.ORDER_STATUS_WEBHOOK: _send_order_status_webhook,
}


def process_notification(kind: str, payload: dict) -> None:
    try:
        handler = HANDLERS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown notification kind: {kind}") from exc
    handler(payload)


def _dispatch(kind: str, payload: dict) -> None:
    if settings.NOTIFICATIONS_ASYNC:
        NotificationJob.objects.create(kind=kind, payload=payload)
        return

    try:
        process_notification(kind, payload)
    except Exception:
        logger.exception("Could not deliver synchronous notification %s.", kind)


def publish_quote_created(quote_id: int) -> None:
    payload = {"quote_id": quote_id}
    _dispatch(NotificationJob.Kind.QUOTE_CUSTOMER_EMAIL, payload)
    if settings.QUOTE_NOTIFICATION_EMAIL:
        _dispatch(NotificationJob.Kind.QUOTE_STAFF_EMAIL, payload)
    if settings.POWER_AUTOMATE_ENABLED:
        _dispatch(NotificationJob.Kind.QUOTE_WEBHOOK, payload)


def publish_quote_ready(quote_id: int) -> None:
    _dispatch(NotificationJob.Kind.QUOTE_READY_EMAIL, {"quote_id": quote_id})


def publish_quote_message(message_id: int) -> None:
    _dispatch(NotificationJob.Kind.QUOTE_MESSAGE_EMAIL, {"message_id": message_id})


def publish_order_status_changed(
    order_id: int,
    previous_status: str,
    new_status: str,
) -> None:
    payload = {
        "order_id": order_id,
        "previous_status": previous_status,
        "new_status": new_status,
    }
    _dispatch(NotificationJob.Kind.ORDER_STATUS_EMAIL, payload)
    if settings.POWER_AUTOMATE_ENABLED:
        _dispatch(NotificationJob.Kind.ORDER_STATUS_WEBHOOK, payload)


def mark_job_sent(job: NotificationJob) -> None:
    job.status = NotificationJob.Status.SENT
    job.processed_at = timezone.now()
    job.last_error = ""
    job.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
