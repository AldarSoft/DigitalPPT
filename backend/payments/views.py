from django.conf import settings
from django.shortcuts import get_object_or_404
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
    PaymentAttemptSerializer,
    PaymentProviderSerializer,
    PaymentSimulationSerializer,
    StorefrontPaymentProviderSerializer,
)
from payments.services import PaymentService
from payments.providers import provider_is_available, provider_is_configured


class PaymentStatusView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        providers = PaymentProvider.objects.all()
        live_processing_available = any(
            provider.is_enabled and not provider.test_mode and provider_is_configured(provider.code)
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

    def post(self, request):
        if not settings.PAYMENTS_STOREFRONT_ENABLED:
            raise NotFound()
        serializer = CheckoutSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_queryset = Order.objects.select_related("user", "quote_request")
        if not request.user.is_staff:
            order_queryset = order_queryset.filter(user=request.user)
        order = get_object_or_404(
            order_queryset,
            order_number=serializer.validated_data["order_number"],
        )
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


class PaymentSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_attempt(self, request, session_id):
        queryset = PaymentAttempt.objects.select_related("order", "provider", "created_by")
        if not request.user.is_staff:
            queryset = queryset.filter(created_by=request.user, order__user=request.user)
        return get_object_or_404(queryset, idempotency_key=session_id)

    def get(self, request, session_id):
        if not settings.PAYMENTS_STOREFRONT_ENABLED:
            raise NotFound()
        attempt = PaymentService.refresh_attempt(
            attempt=self.get_attempt(request, session_id),
        )
        return Response(PaymentAttemptSerializer(attempt, context={"request": request}).data)


class PaymentSessionSimulateView(PaymentSessionDetailView):
    throttle_scope = "payment_test"

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
