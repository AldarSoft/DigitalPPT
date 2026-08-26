from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings


PROVIDER_REQUIREMENTS = {
    "stripe": ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"),
    "paypal": ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID"),
    "qpay": ("QPAY_CLIENT_ID", "QPAY_CLIENT_SECRET", "QPAY_INVOICE_CODE"),
    "bank_transfer": ("PAYMENT_BANK_TRANSFER_INSTRUCTIONS",),
}


@dataclass(frozen=True)
class ProviderCheckoutSession:
    checkout_url: str
    external_reference: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class VerifiedProviderCallback:
    event_id: str
    payment_reference: str
    transaction_id: str
    outcome: str
    amount: str
    currency: str


class PaymentProviderAdapter(Protocol):
    """Contract a bank-specific adapter must satisfy before it is enabled."""

    code: str

    def create_checkout(self, *, attempt) -> ProviderCheckoutSession: ...

    def verify_callback(self, *, headers, body: bytes) -> VerifiedProviderCallback: ...

    def reconcile_pending(self, *, attempts) -> int: ...


# Deliberately empty: bank credentials alone must never enable a live flow.
# Register an adapter only after its API request, signed callback, and sandbox
# behavior are verified against the provider's documentation.
LIVE_PROVIDER_ADAPTERS: dict[str, PaymentProviderAdapter] = {}


def get_provider_adapter(code: str) -> PaymentProviderAdapter | None:
    return LIVE_PROVIDER_ADAPTERS.get(code)


def provider_is_configured(code: str) -> bool:
    required = PROVIDER_REQUIREMENTS.get(code, ())
    return bool(required) and all(bool(getattr(settings, key, "")) for key in required)


def provider_is_available(provider) -> bool:
    if not provider.is_enabled:
        return False
    if provider.test_mode:
        return bool(settings.DEBUG and settings.PAYMENTS_DEVELOPMENT_SIMULATOR)
    return bool(get_provider_adapter(provider.code) and provider_is_configured(provider.code))


def provider_integration_state(provider) -> str:
    if not provider.is_enabled:
        return "disabled"
    if provider.test_mode:
        return "development_simulator" if provider_is_available(provider) else "development_unavailable"
    if not provider_is_configured(provider.code):
        return "credentials_missing"
    if not get_provider_adapter(provider.code):
        return "adapter_not_implemented"
    return "ready"
