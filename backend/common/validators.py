import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from rest_framework import serializers


PHONE_PATTERN = re.compile(r"^[+]?[0-9][0-9\s().-]{5,19}$")

# Administrator-configured links may point at in-application paths, page
# anchors, HTTPS destinations, or mailto/tel handlers only.
STORE_URL_ALLOWED_SCHEMES = frozenset({"https", "mailto", "tel"})


def validate_store_url(value):
    """Validate a store link; empty and relative/hash values are allowed."""
    value = (value or "").strip()
    if not value:
        return value
    if value.startswith("#"):
        return value
    if value.startswith("/") and not value.startswith(("//", "/\\")):
        return value
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in STORE_URL_ALLOWED_SCHEMES:
        raise ValidationError(
            "Links must use https, mailto, or tel, or be a relative path."
        )
    return value


def validate_phone(value):
    if value and not PHONE_PATTERN.fullmatch(value.strip()):
        raise serializers.ValidationError("Enter a valid phone number.")
    return value
