from uuid import uuid4

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import parsers, status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from common.permissions import IsAdminOrReadOnly
from common.images import sanitize_uploaded_image
from products.models import Category, InventoryAdjustment, Product
from orders.models import Order, OrderItem
from orders.models import InventoryReservation
from products.serializers import (
    CategorySerializer,
    CategoryWriteSerializer,
    AdminProductSerializer,
    ProductSerializer,
    ProductWriteSerializer,
    ProductImageUploadRequestSerializer,
    ProductImageUploadResponseSerializer,
    InventoryAdjustmentSerializer,
)


class ProductImageUploadView(APIView):
    permission_classes = [IsAdminUser]
    throttle_scope = "image_upload"
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    @extend_schema(
        request=ProductImageUploadRequestSerializer,
        responses={201: ProductImageUploadResponseSerializer},
    )
    def post(self, request):
        image = request.FILES.get("image")
        if not image:
            return Response({"detail": "Image file is required."}, status=status.HTTP_400_BAD_REQUEST)

        sanitized_image, extension = sanitize_uploaded_image(image)
        filename = f"products/{uuid4().hex}{extension}"
        saved_path = default_storage.save(filename, sanitized_image)
        image_url = default_storage.url(saved_path)

        return Response({"image_url": image_url}, status=status.HTTP_201_CREATED)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.select_related("parent").prefetch_related("children")
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ("name", "slug")
    ordering_fields = ("name", "created_at")
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return CategoryWriteSerializer
        return CategorySerializer


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrReadOnly]
    search_fields = (
        "name",
        "sku",
        "brand",
        "short_description",
        "description",
        "category__name",
        "category__slug",
        "current_price_value",
        "price",
        "sale_price",
        "inventory_quantity",
        "specifications__key",
        "specifications__value",
    )
    ordering_fields = (
        "name",
        "price",
        "current_price_value",
        "created_at",
        "updated_at",
        "inventory_quantity",
        "is_featured",
    )
    lookup_field = "slug"

    def get_queryset(self):
        reserved_quantity = (
            InventoryReservation.objects.filter(
                product_id=OuterRef("pk"),
                status=InventoryReservation.Status.RESERVED,
            )
            .values("product_id")
            .annotate(total=Sum("quantity"))
            .values("total")[:1]
        )
        backordered_quantity = (
            OrderItem.objects.filter(
                product_id=OuterRef("pk"),
                backordered_quantity__gt=0,
                order__status=Order.Status.BACKORDERED,
            )
            .values("product_id")
            .annotate(total=Sum("backordered_quantity"))
            .values("total")[:1]
        )
        queryset = Product.objects.with_catalog_relations().annotate(
            current_price_value=Coalesce(
                "sale_price",
                "price",
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            reserved_inventory_quantity=Coalesce(
                Subquery(reserved_quantity, output_field=IntegerField()),
                Value(0),
            ),
            backordered_inventory_quantity=Coalesce(
                Subquery(backordered_quantity, output_field=IntegerField()),
                Value(0),
            ),
        ).annotate(
            sellable_inventory_quantity=ExpressionWrapper(
                F("inventory_quantity") - F("reserved_inventory_quantity"),
                output_field=IntegerField(),
            ),
        )
        if not (self.request.user and self.request.user.is_staff):
            queryset = queryset.public()

        category_slug = self.request.query_params.get("category")
        featured = self.request.query_params.get("featured")
        best_sellers = self.request.query_params.get("best_sellers")
        stock = self.request.query_params.get("stock")
        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")
        status_value = self.request.query_params.get("status")
        licensing_role = self.request.query_params.get("licensing_role")

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        if featured in {"true", "1"}:
            queryset = queryset.filter(is_featured=True)
        if stock in {"true", "1"}:
            queryset = queryset.filter(
                Q(sellable_inventory_quantity__gt=0)
                | Q(licensing_role=Product.LicensingRole.LICENSE_PRODUCT)
            )
        if stock == "out":
            queryset = queryset.filter(
                sellable_inventory_quantity__lte=0,
                licensing_role__in=(
                    Product.LicensingRole.STANDARD,
                    Product.LicensingRole.LICENSED_PRODUCT,
                ),
            )
        if stock == "low":
            queryset = queryset.filter(sellable_inventory_quantity__gt=0, sellable_inventory_quantity__lte=5)
        if stock == "healthy":
            queryset = queryset.filter(sellable_inventory_quantity__gt=5)
        if best_sellers in {"true", "1"}:
            sold_quantity = (
                OrderItem.objects.filter(
                    product_id=OuterRef("pk"),
                    order__status=Order.Status.COMPLETED,
                )
                .values("product_id")
                .annotate(total=Sum("quantity"))
                .values("total")
            )
            queryset = queryset.annotate(
                sold_quantity=Coalesce(
                    Subquery(sold_quantity, output_field=IntegerField()),
                    Value(0),
                )
            ).order_by("-sold_quantity", "-created_at")
        if min_price:
            queryset = queryset.filter(current_price_value__gte=min_price)
        if max_price:
            queryset = queryset.filter(current_price_value__lte=max_price)
        if status_value and self.request.user and self.request.user.is_staff:
            queryset = queryset.filter(status=status_value)
        if licensing_role and self.request.user and self.request.user.is_staff:
            queryset = queryset.filter(licensing_role=licensing_role)
        return queryset

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy", "inventory_adjust"}:
            return [IsAdminUser()]
        return [IsAdminOrReadOnly()]

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ProductWriteSerializer
        if self.request.user and self.request.user.is_staff:
            return AdminProductSerializer
        return ProductSerializer

    def perform_update(self, serializer):
        previous_inventory = serializer.instance.inventory_quantity
        product = serializer.save()
        if product.is_stock_tracked and product.inventory_quantity > previous_inventory:
            from orders.services import InventoryReservationService

            transaction.on_commit(
                lambda product_id=product.pk: InventoryReservationService.reserve_backorders_for_product(
                    product_id=product_id
                )
            )

    @action(detail=True, methods=["post"], url_path="inventory-adjust")
    @transaction.atomic
    def inventory_adjust(self, request, slug=None):
        product = Product.objects.select_for_update().get(slug=slug)
        if not product.is_stock_tracked:
            return Response(
                {"detail": "License products do not use physical inventory."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = InventoryAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reserved_quantity = InventoryReservation.objects.filter(
            product=product,
            status=InventoryReservation.Status.RESERVED,
        ).aggregate(total=Coalesce(Sum("quantity"), Value(0)))["total"]
        quantity_before = product.inventory_quantity
        quantity_after = (
            quantity_before + data["quantity"]
            if data["mode"] == InventoryAdjustment.Mode.ADD
            else data["quantity"]
        )
        if quantity_after < reserved_quantity:
            return Response(
                {
                    "quantity": (
                        f"On-hand stock cannot be lower than the {reserved_quantity} units "
                        "reserved for paid orders."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        product.inventory_quantity = quantity_after
        product.save(update_fields=["inventory_quantity", "updated_at"])
        InventoryAdjustment.objects.create(
            product=product,
            performed_by=request.user,
            mode=data["mode"],
            quantity=data["quantity"],
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reason=data["reason"],
        )
        if quantity_after > quantity_before:
            from orders.services import InventoryReservationService

            InventoryReservationService.reserve_backorders_for_product(product_id=product.pk)

        product = self.get_queryset().get(pk=product.pk)
        return Response(self.get_serializer(product).data)

    @action(detail=False, methods=["get"], url_path=r"by-id/(?P<product_id>\d+)")
    def by_id(self, request, product_id=None):
        product = self.get_queryset().filter(pk=product_id).first()
        if not product:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(product).data)
