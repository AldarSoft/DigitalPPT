from __future__ import annotations

from django.conf import settings


PROVIDER_REQUIREMENTS = {
    "stripe": ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"),
    "paypal": ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID"),
    "qpay": ("QPAY_CLIENT_ID", "QPAY_CLIENT_SECRET", "QPAY_INVOICE_CODE"),
    "bank_transfer": ("PAYMENT_BANK_TRANSFER_INSTRUCTIONS",),
}

# Add a provider code only when its create-session and verified-webhook adapter
# are implemented. Credentials alone must never expose an incomplete live flow.
LIVE_PROVIDER_ADAPTERS = frozenset()


def provider_is_configured(code: str) -> bool:
    required = PROVIDER_REQUIREMENTS.get(code, ())
    return bool(required) and all(bool(getattr(settings, key, "")) for key in required)


def provider_is_available(provider) -> bool:
    if not provider.is_enabled:
        return False
    if provider.test_mode:
        return bool(settings.DEBUG and settings.PAYMENTS_DEVELOPMENT_SIMULATOR)
    return provider.code in LIVE_PROVIDER_ADAPTERS and provider_is_configured(provider.code)
