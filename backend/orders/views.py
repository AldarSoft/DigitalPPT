from django.db.models import Exists, OuterRef, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from common.permissions import CanManageOrders
from orders.models import Order
from payments.models import PaymentAttempt
from orders.serializers import (
    CheckoutSerializer,
    AdminManualOrderSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    OrderStatusSerializer,
    ShipmentCreateSerializer,
)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related(
        "user",
        "organization",
        "quote_request",
        "renewal_license__organization",
        "renewal_license__license_product",
    ).prefetch_related("items__product", "shipments__items")
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
        if self.action in {"create", "ship"}:
            return [CanManageOrders()]
        if self.action in {"partial_update", "update", "destroy"}:
            return [CanManageOrders()]
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
            "draft": [Order.Status.DRAFT],
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
            if self.request.user.is_superuser or self.request.user.has_perm("users.manage_orders"):
                return queryset
            return queryset.none()
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.none()
        queryset = queryset.exclude(status=Order.Status.DRAFT)
        from licensing.models import OrganizationMembership

        owner_organizations = OrganizationMembership.objects.filter(
            user=self.request.user,
            is_active=True,
            role=OrganizationMembership.Role.OWNER,
            organization__is_active=True,
        ).values("organization_id")
        organization_id = self.request.query_params.get("organization")
        if organization_id:
            if not organization_id.isdigit():
                return queryset.none()
            queryset = queryset.filter(organization_id=organization_id)
            # Only Owners and authorized staff see organization orders;
            # License Managers see their own orders only.
            if not owner_organizations.filter(
                organization_id=int(organization_id)
            ).exists():
                return queryset.filter(user=self.request.user)
            return queryset.distinct()
        return queryset.filter(
            Q(user=self.request.user) | Q(organization_id__in=owner_organizations)
        ).distinct()

    def get_serializer_class(self):
        if self.action == "manual":
            return AdminManualOrderSerializer
        if self.action == "create":
            return OrderCreateSerializer
        if self.action in {"partial_update", "update"}:
            return OrderStatusSerializer
        return OrderSerializer

    @action(detail=False, methods=["post"], permission_classes=[CanManageOrders], url_path="manual")
    def manual(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(
            OrderSerializer(order, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], permission_classes=[CanManageOrders], url_path="ship")
    def ship(self, request, order_number=None):
        serializer = ShipmentCreateSerializer(
            data=request.data,
            context={
                "request": request,
                "order_number": order_number,
            },
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(
            OrderSerializer(order, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

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
