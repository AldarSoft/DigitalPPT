from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.db import models
from rest_framework import serializers

from orders.models import Order
from payments.models import PaymentAttempt, PaymentProvider
from payments.providers import provider_is_configured


class PaymentProviderSerializer(serializers.ModelSerializer):
    api_connected = serializers.SerializerMethodField()

    class Meta:
        model = PaymentProvider
        fields = ("id", "code", "display_name", "is_enabled", "test_mode", "api_connected", "sort_order")
        read_only_fields = ("id", "code", "test_mode", "api_connected", "sort_order")

    def get_api_connected(self, obj) -> bool:
        return provider_is_configured(obj.code)


class StorefrontPaymentProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentProvider
        fields = ("code", "display_name", "test_mode", "sort_order")


class PaymentAttemptSerializer(serializers.ModelSerializer):
    session_id = serializers.UUIDField(source="idempotency_key", read_only=True)
    checkout_url = serializers.SerializerMethodField()
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)
    provider_code = serializers.CharField(source="provider.code", read_only=True)
    provider_name = serializers.CharField(source="provider.display_name", read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = PaymentAttempt
        fields = (
            "id", "reference", "session_id", "checkout_url", "order_number", "order_status", "provider_code",
            "provider_name", "amount", "currency", "status", "is_test", "external_reference",
            "failure_message", "created_by_email", "expires_at", "paid_at", "created_at",
        )

    def get_checkout_url(self, obj) -> str:
        provider_url = obj.metadata.get("checkout_url") if isinstance(obj.metadata, dict) else ""
        if provider_url:
            return provider_url
        if obj.is_test and settings.PAYMENTS_DEVELOPMENT_SIMULATOR:
            return f"{settings.FRONTEND_URL.rstrip('/')}/payment?session={obj.idempotency_key}"
        return ""


class BillingDetailsSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=32, allow_blank=True, required=False)
    company = serializers.CharField(max_length=255, allow_blank=True, required=False)
    address = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=120)
    state = serializers.CharField(max_length=120, allow_blank=True, required=False)
    postal_code = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=120)


class CheckoutSessionCreateSerializer(serializers.Serializer):
    order_number = serializers.CharField(max_length=40)
    provider = serializers.SlugRelatedField(
        slug_field="code",
        queryset=PaymentProvider.objects.filter(is_enabled=True),
    )
    idempotency_key = serializers.UUIDField()
    billing = BillingDetailsSerializer()


class DevelopmentConfirmationSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(
        choices=(PaymentAttempt.Status.SUCCEEDED, PaymentAttempt.Status.FAILED),
    )


class PaymentSimulationSerializer(serializers.Serializer):
    class Outcome(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        PENDING = "pending", "Pending"

    order_number = serializers.SlugRelatedField(
        slug_field="order_number",
        queryset=Order.objects.select_related("quote_request"),
        source="order",
    )
    provider = serializers.SlugRelatedField(
        slug_field="code",
        queryset=PaymentProvider.objects.filter(is_enabled=True, test_mode=True),
    )
    outcome = serializers.ChoiceField(choices=Outcome.choices, default=Outcome.SUCCEEDED)

    def create(self, validated_data):
        order = validated_data["order"]
        provider = validated_data["provider"]
        outcome = validated_data["outcome"]
        request = self.context["request"]
        return PaymentAttempt.objects.create(
            order=order,
            provider=provider,
            amount=order.total,
            currency="USD",
            status=outcome,
            is_test=True,
            external_reference=f"test_{provider.code}_{uuid4().hex}",
            failure_message="Simulated provider decline." if outcome == self.Outcome.FAILED else "",
            metadata={"simulation": True},
            created_by=request.user,
        )
