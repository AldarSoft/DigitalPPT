from django.db.models import Exists, OuterRef
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from orders.models import Order
from payments.models import PaymentAttempt
from orders.serializers import (
    CheckoutSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    OrderStatusSerializer,
)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related("user", "quote_request").prefetch_related("items__product")
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_field = "order_number"
    search_fields = (
        "=id",
        "order_number",
        "quote_request__quote_number",
        "customer_email",
        "customer_first_name",
        "customer_last_name",
        "company_name",
    )
    ordering_fields = ("created_at", "total", "status")

    def get_permissions(self):
        if self.action == "create":
            return [IsAdminUser()]
        if self.action in {"partial_update", "update", "destroy"}:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        successful_payment = PaymentAttempt.objects.filter(
            order_id=OuterRef("pk"),
            status=PaymentAttempt.Status.SUCCEEDED,
        )
        queryset = queryset.annotate(
            has_successful_payment=Exists(successful_payment)
        ).exclude(
            status=Order.Status.CANCELLED,
            has_successful_payment=False,
        )
        status_value = self.request.query_params.get("status")
        display_status = self.request.query_params.get("display_status")
        display_statuses = {
            "pending": [Order.Status.PENDING],
            "processing": [Order.Status.SCHEDULED, Order.Status.PROCESSING],
            "completed": [Order.Status.COMPLETED],
            "cancelled": [Order.Status.CANCELLED],
        }
        if display_status in display_statuses:
            queryset = queryset.filter(status__in=display_statuses[display_status])
        elif status_value:
            queryset = queryset.filter(status=status_value)
        if self.request.user and self.request.user.is_staff:
            return queryset
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.none()
        return queryset.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action in {"partial_update", "update"}:
            return OrderStatusSerializer
        return OrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        response_serializer = OrderSerializer(
            order,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class CheckoutViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CheckoutSerializer
    throttle_scope = "checkout"

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(
            OrderSerializer(order, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )
