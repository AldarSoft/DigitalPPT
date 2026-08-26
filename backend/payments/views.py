from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order
from payments.models import PaymentAttempt, PaymentProvider
from payments.serializers import (
    CheckoutSessionCreateSerializer,
    DevelopmentConfirmationSerializer,
    LicenseRenewalCheckoutSessionCreateSerializer,
    PaymentAttemptSerializer,
    PaymentProviderSerializer,
    PaymentSimulationSerializer,
    StorefrontPaymentProviderSerializer,
)
from payments.providers import get_provider_adapter, provider_is_available
from payments.services import PaymentProviderCallbackService, PaymentService


class PaymentStatusView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Get administrative payment availability",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        providers = PaymentProvider.objects.all()
        live_processing_available = any(
            provider.is_enabled and not provider.test_mode and provider_is_available(provider)
            for provider in providers
        )
        return Response({
            "storefront_enabled": settings.PAYMENTS_STOREFRONT_ENABLED,
            "live_processing_available": live_processing_available,
            "test_mode": not live_processing_available,
            "providers": PaymentProviderSerializer(providers, many=True).data,
        })


class StorefrontPaymentStatusView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get storefront payment availability",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        providers = [
            provider for provider in PaymentProvider.objects.filter(is_enabled=True)
            if provider_is_available(provider)
        ]
        return Response({
            "storefront_enabled": bool(settings.PAYMENTS_STOREFRONT_ENABLED and providers),
            "development_simulator": settings.PAYMENTS_DEVELOPMENT_SIMULATOR,
            "providers": StorefrontPaymentProviderSerializer(providers, many=True).data
            if settings.PAYMENTS_STOREFRONT_ENABLED else [],
        })


class CheckoutSessionCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "payment_test"

    @extend_schema(
        summary="Create or reuse a payment checkout session",
        request=CheckoutSessionCreateSerializer,
        responses={200: PaymentAttemptSerializer, 201: PaymentAttemptSerializer},
    )
    def post(self, request):
        if not settings.PAYMENTS_STOREFRONT_ENABLED:
            raise NotFound()
        serializer = CheckoutSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_queryset = Order.objects.select_related("user", "organization", "quote_request")
        order = get_object_or_404(
            order_queryset,
            order_number=serializer.validated_data["order_number"],
        )
        if not PaymentService.can_pay_order(user=request.user, order=order):
            raise NotFound()
        attempt, created = PaymentService.start_checkout(
            user=request.user,
            order=order,
            provider=serializer.validated_data["provider"],
            idempotency_key=serializer.validated_data["idempotency_key"],
            billing=serializer.validated_data["billing"],
        )
        return Response(
            PaymentAttemptSerializer(attempt, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class LicenseRenewalCheckoutSessionCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "payment_test"

    @extend_schema(
        summary="Create or reuse a selected-license renewal payment session",
        request=LicenseRenewalCheckoutSessionCreateSerializer,
        responses={200: PaymentAttemptSerializer, 201: PaymentAttemptSerializer},
    )
    def post(self, request):
        if not settings.PAYMENTS_STOREFRONT_ENABLED:
            raise NotFound()
        serializer = LicenseRenewalCheckoutSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt, created = PaymentService.start_license_renewal_checkout(
            user=request.user,
            license_number=serializer.validated_data["license_number"],
            organization_id=serializer.validated_data.get("organization"),
            provider=serializer.validated_data["provider"],
            idempotency_key=serializer.validated_data["idempotency_key"],
            billing=serializer.validated_data["billing"],
        )
        return Response(
            PaymentAttemptSerializer(attempt, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PaymentSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_attempt(self, request, session_id):
        attempt = get_object_or_404(
            PaymentAttempt.objects.select_related("order__organization", "renewal_license__organization", "provider", "created_by"),
            idempotency_key=session_id,
        )
        if not PaymentService.can_pay_attempt(user=request.user, attempt=attempt) and attempt.created_by_id != request.user.id:
            raise NotFound()
        return attempt

    @extend_schema(
        summary="Get a payment checkout session",
        responses=PaymentAttemptSerializer,
    )
    def get(self, request, session_id):
        if not settings.PAYMENTS_STOREFRONT_ENABLED:
            raise NotFound()
        attempt = PaymentService.refresh_attempt(
            attempt=self.get_attempt(request, session_id),
        )
        return Response(PaymentAttemptSerializer(attempt, context={"request": request}).data)


class PaymentSessionSimulateView(PaymentSessionDetailView):
    throttle_scope = "payment_test"

    @extend_schema(
        summary="Simulate a development payment result",
        request=DevelopmentConfirmationSerializer,
        responses=PaymentAttemptSerializer,
    )
    def post(self, request, session_id):
        if not (
            settings.DEBUG
            and settings.PAYMENTS_STOREFRONT_ENABLED
            and settings.PAYMENTS_DEVELOPMENT_SIMULATOR
        ):
            raise NotFound()
        input_serializer = DevelopmentConfirmationSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        attempt = self.get_attempt(request, session_id)
        if not attempt.is_test:
            raise NotFound()
        attempt = PaymentService.simulate_checkout(
            attempt=attempt,
            user=request.user,
            outcome=input_serializer.validated_data["outcome"],
        )
        return Response(PaymentAttemptSerializer(attempt, context={"request": request}).data)


class PaymentProviderCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Receive a verified live-payment provider callback",
        request=OpenApiTypes.BINARY,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, provider_code):
        provider = get_object_or_404(
            PaymentProvider.objects.filter(code=provider_code, is_enabled=True, test_mode=False)
        )
        adapter = get_provider_adapter(provider.code)
        if not adapter or not provider_is_available(provider):
            raise NotFound()
        body = request.body
        if len(body) > settings.PAYMENT_PROVIDER_CALLBACK_MAX_BODY_BYTES:
            return Response(
                {"detail": "Callback body is too large."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        callback = adapter.verify_callback(headers=request.headers, body=body)
        event, created = PaymentProviderCallbackService.process(
            provider=provider,
            callback=callback,
            payload=body,
        )
        return Response(
            {"event_id": event.event_id, "status": event.status, "duplicate": not created},
            status=status.HTTP_200_OK,
        )


class PaymentProviderViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = PaymentProvider.objects.all()
    serializer_class = PaymentProviderSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "patch", "head", "options"]


class PaymentAttemptViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = PaymentAttempt.objects.select_related("order", "provider", "created_by")
    serializer_class = PaymentAttemptSerializer
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ("reference", "order__order_number", "provider__display_name", "external_reference")
    ordering_fields = ("created_at", "amount", "status")
    throttle_scope = "payment_test"

    def create(self, request, *args, **kwargs):
        input_serializer = PaymentSimulationSerializer(data=request.data, context={"request": request})
        input_serializer.is_valid(raise_exception=True)
        attempt = input_serializer.save()
        return Response(PaymentAttemptSerializer(attempt).data, status=status.HTTP_201_CREATED)
