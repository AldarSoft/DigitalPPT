from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from rest_framework.exceptions import ValidationError


CLAIM_SALT = "quotes.guest-claim"


def make_guest_quote_claim_token(quote_request) -> str:
    return signing.dumps(
        {
            "quote_id": quote_request.pk,
            "requester_email": quote_request.requester_email.lower(),
        },
        salt=CLAIM_SALT,
        compress=True,
    )


def validate_guest_quote_claim_token(*, quote_request, token: str) -> None:
    try:
        payload = signing.loads(
            token,
            salt=CLAIM_SALT,
            max_age=settings.QUOTE_GUEST_CLAIM_TIMEOUT,
        )
    except signing.BadSignature as exc:
        raise ValidationError({"token": "This quote access link is invalid or expired."}) from exc

    if (
        payload.get("quote_id") != quote_request.pk
        or payload.get("requester_email") != quote_request.requester_email.lower()
    ):
        raise ValidationError({"token": "This quote access link is invalid or expired."})


def guest_quote_claim_url(quote_request) -> str:
    query = urlencode({
        "quote": quote_request.quote_number,
        "token": make_guest_quote_claim_token(quote_request),
    })
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/claim-quote?{query}"
