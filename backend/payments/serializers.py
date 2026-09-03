from __future__ import annotations

from django.conf import settings
from django.db import models
from rest_framework import serializers

from orders.models import Order
from payments.models import PaymentAttempt, PaymentProvider, PaymentStatusEvent
from payments.providers import provider_integration_state, provider_is_configured
from payments.services import PaymentService


class PaymentProviderSerializer(serializers.ModelSerializer):
    api_connected = serializers.SerializerMethodField()
    integration_state = serializers.SerializerMethodField()

    class Meta:
        model = PaymentProvider
        fields = (
            "id", "code", "display_name", "is_enabled", "test_mode",
            "is_customer_available", "api_connected", "integration_state", "sort_order",
        )
        read_only_fields = (
            "id", "code", "test_mode", "api_connected", "integration_state", "sort_order",
        )

    def get_api_connected(self, obj) -> bool:
        return provider_is_configured(obj.code)

    def get_integration_state(self, obj) -> str:
        return provider_integration_state(obj)

    def validate(self, attrs):
        instance = self.instance
        test_mode = instance.test_mode if instance else attrs.get("test_mode", True)
        customer_available = attrs.get(
            "is_customer_available",
            instance.is_customer_available if instance else False,
        )
        provider_code = instance.code if instance else attrs.get("code")
        if provider_code != PaymentProvider.Code.BANK_TRANSFER and test_mode and customer_available and not (
            settings.DEBUG and settings.PAYMENTS_DEVELOPMENT_SIMULATOR
        ):
            raise serializers.ValidationError({
                "is_customer_available": "Test payment providers cannot be offered to production customers."
            })
        return attrs


class StorefrontPaymentProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentProvider
        fields = ("code", "display_name", "test_mode", "sort_order")


class BankTransferConfirmationSerializer(serializers.Serializer):
    bank_transaction_reference = serializers.CharField(max_length=255)
    internal_note = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    current_password = serializers.CharField(write_only=True)
    confirmed_invoice_match = serializers.BooleanField()

    def validate_bank_transaction_reference(self, value):
        if not value.strip():
            raise serializers.ValidationError("Enter the bank transaction reference.")
        return value.strip()

    def validate_current_password(self, value):
        request = self.context.get("request")
        if not request or not request.user.check_password(value):
            raise serializers.ValidationError("Enter your current password to confirm this payment.")
        return value

    def validate_confirmed_invoice_match(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Confirm that the invoice reference and exact amount match the bank statement."
            )
        return value


class BankTransferRejectionSerializer(serializers.Serializer):
    bank_transaction_reference = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    reason = serializers.CharField(max_length=1000, allow_blank=False, trim_whitespace=True)
    current_password = serializers.CharField(write_only=True)
    confirmed_rejection = serializers.BooleanField()

    def validate_current_password(self, value):
        request = self.context.get("request")
        if not request or not request.user.check_password(value):
            raise serializers.ValidationError("Enter your current password to reject this payment.")
        return value

    def validate_confirmed_rejection(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Confirm that this transfer must remain unpaid."
            )
        return value


class PaymentStatusEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, allow_null=True)

    class Meta:
        model = PaymentStatusEvent
        fields = (
            "id",
            "event_type",
            "previous_status",
            "new_status",
            "invoice_reference",
            "amount",
            "currency",
            "external_reference",
            "reason",
            "actor_email",
            "created_at",
        )
        read_only_fields = fields


class PaymentAttemptSerializer(serializers.ModelSerializer):
    session_id = serializers.UUIDField(source="idempotency_key", read_only=True)
    checkout_url = serializers.SerializerMethodField()
    order_number = serializers.CharField(source="order.order_number", read_only=True, allow_null=True)
    order_status = serializers.CharField(source="order.status", read_only=True, allow_null=True)
    renewal_license_number = serializers.CharField(source="renewal_license.license_number", read_only=True, allow_null=True)
    provider_code = serializers.CharField(source="provider.code", read_only=True)
    provider_name = serializers.CharField(source="provider.display_name", read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    status_events = PaymentStatusEventSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentAttempt
        fields = (
            "id", "reference", "session_id", "checkout_url", "order_number", "order_status", "renewal_license_number", "provider_code",
            "provider_name", "amount", "currency", "status", "is_test", "external_reference",
            "failure_message", "created_by_email", "expires_at", "paid_at", "created_at",
            "status_events",
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
        queryset=PaymentProvider.objects.filter(is_enabled=True, is_customer_available=True).exclude(
            code=PaymentProvider.Code.BANK_TRANSFER
        ),
    )
    idempotency_key = serializers.UUIDField()
    billing = BillingDetailsSerializer()


class LicenseRenewalCheckoutSessionCreateSerializer(serializers.Serializer):
    license_number = serializers.CharField(max_length=64)
    organization = serializers.IntegerField(required=False, allow_null=True)
    provider = serializers.SlugRelatedField(
        slug_field="code",
        queryset=PaymentProvider.objects.filter(is_enabled=True, is_customer_available=True).exclude(
            code=PaymentProvider.Code.BANK_TRANSFER
        ),
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
        request = self.context["request"]
        return PaymentService.create_admin_simulation(
            user=request.user,
            order=validated_data["order"],
            provider=validated_data["provider"],
            outcome=validated_data["outcome"],
        )
