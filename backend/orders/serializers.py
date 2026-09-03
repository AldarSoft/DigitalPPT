from __future__ import annotations

from datetime import timedelta

from rest_framework import serializers
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from quotes.models import QuoteRequest

from orders.models import Order, OrderItem, Shipment, ShipmentItem
from orders.services import OrderService
from common.validators import validate_phone
from products.models import Product
from licensing.models import Organization


class OrderItemSerializer(serializers.ModelSerializer):
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    image_url = serializers.SerializerMethodField()
    available_stock = serializers.SerializerMethodField()
    licensing_role = serializers.SerializerMethodField()
    license_capacity = serializers.SerializerMethodField()
    license_term_days = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product",
            "product_slug",
            "product_name",
            "sku",
            "unit_price",
            "quantity",
            "reserved_quantity",
            "backordered_quantity",
            "fulfillment_status",
            "line_total",
            "image_url",
            "available_stock",
            "licensing_role",
            "license_capacity",
            "license_term_days",
        )

    def get_image_url(self, obj) -> str:
        image = obj.product.images.order_by("-is_primary", "sort_order", "id").first() if obj.product else None
        return image.image_url if image else ""

    def get_available_stock(self, obj) -> int | None:
        if not obj.product:
            return None
        from orders.services import InventoryReservationService

        reserved = InventoryReservationService.reserved_quantities(product_ids=[obj.product_id])
        return InventoryReservationService.available_quantity(
            product=obj.product,
            reserved_quantity=reserved.get(obj.product_id, 0),
        )

    def get_licensing_role(self, obj) -> str | None:
        return obj.product.licensing_role if obj.product else None

    def get_license_capacity(self, obj) -> int | None:
        return obj.product.license_capacity if obj.product else None

    def get_license_term_days(self, obj) -> int | None:
        return obj.product.license_term_days if obj.product else None


class ShipmentItemSerializer(serializers.ModelSerializer):
    order_item_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShipmentItem
        fields = (
            "id",
            "order_item_id",
            "quantity",
            "product_name",
            "sku",
        )


class ShipmentSerializer(serializers.ModelSerializer):
    items = ShipmentItemSerializer(many=True, read_only=True)
    carrier = serializers.CharField(read_only=True, allow_blank=True)
    tracking_number = serializers.CharField(read_only=True, allow_blank=True)

    class Meta:
        model = Shipment
        fields = (
            "id",
            "shipment_number",
            "carrier",
            "tracking_number",
            "notes",
            "shipped_at",
            "shipping_address",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "items",
            "created_at",
        )


class ShipmentItemCreateSerializer(serializers.Serializer):
    order_item_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=9999)


class ShipmentCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    items = ShipmentItemCreateSerializer(many=True, allow_empty=False)
    carrier = serializers.CharField(required=False, allow_blank=True, max_length=120)
    tracking_number = serializers.CharField(required=False, allow_blank=True, max_length=120)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_items(self, value):
        item_ids = [item["order_item_id"] for item in value]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError("Each order item can appear only once.")
        return value

    def create(self, validated_data):
        from orders.services import ShipmentService

        return ShipmentService.create_shipment(
            order_number=self.context["order_number"],
            idempotency_key=validated_data["idempotency_key"],
            items=validated_data["items"],
            carrier=validated_data.get("carrier", ""),
            tracking_number=validated_data.get("tracking_number", ""),
            notes=validated_data.get("notes", ""),
            actor=self.context["request"].user,
        )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shipments = ShipmentSerializer(many=True, read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    organization_id = serializers.IntegerField(read_only=True)
    renewal_license_number = serializers.CharField(
        source="renewal_license.license_number",
        read_only=True,
        allow_null=True,
    )
    renewal = serializers.SerializerMethodField()
    quote_number = serializers.CharField(source="quote_request.quote_number", read_only=True)
    is_paid = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "quote_number",
            "is_paid",
            "source",
            "user_id",
            "organization_id",
            "renewal_license_number",
            "renewal",
            "status",
            "customer_first_name",
            "customer_last_name",
            "customer_email",
            "customer_phone",
            "company_name",
            "shipping_address",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "subtotal",
            "tax_amount",
            "shipping_fee",
            "total",
            "stock_deducted",
            "notes",
            "items",
            "shipments",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("stock_deducted",)

    def get_is_paid(self, obj) -> bool:
        from payments.models import PaymentAttempt

        return obj.payment_attempts.filter(
            status=PaymentAttempt.Status.SUCCEEDED
        ).exists()

    @extend_schema_field(serializers.DictField)
    def get_renewal(self, obj) -> dict | None:
        license = obj.renewal_license
        if license is None:
            return None
        term_days = license.license_product.license_term_days or 0
        current_expiry = license.expires_on
        projected_expiry = (
            max(timezone.localdate(), current_expiry or timezone.localdate())
            + timedelta(days=term_days)
            if term_days
            else None
        )
        return {
            "license_number": license.license_number,
            "license_name": license.name,
            "organization_name": license.organization.name,
            "current_expires_on": current_expiry,
            "projected_expires_on": projected_expiry,
            "term_days": term_days or None,
        }


class OrderCreateItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ("product", "product_name", "sku", "unit_price", "quantity")
        extra_kwargs = {
            "product_name": {"required": False, "allow_blank": True},
            "sku": {"required": False, "allow_blank": True},
            "unit_price": {"required": False},
        }

    def validate(self, attrs):
        if not attrs.get("product") and not attrs.get("product_name"):
            raise serializers.ValidationError(
                "Each order item requires a product reference or a product_name."
            )
        return attrs


class CheckoutItemSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.public()
    )
    quantity = serializers.IntegerField(min_value=1, max_value=999)
    automatic = serializers.BooleanField(default=False, write_only=True)


class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderCreateItemSerializer(many=True)
    quote_number = serializers.CharField(write_only=True, required=False)
    customer_phone = serializers.CharField(required=False, allow_blank=True, validators=[validate_phone])

    class Meta:
        model = Order
        fields = (
            "organization",
            "quote_number",
            "customer_first_name",
            "customer_last_name",
            "customer_email",
            "customer_phone",
            "company_name",
            "shipping_address",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "notes",
            "items",
        )

    def validate(self, attrs):
        quote_number = attrs.get("quote_number")
        if not quote_number:
            return attrs

        quote_request = QuoteRequest.objects.filter(quote_number=quote_number).first()
        if not quote_request:
            raise serializers.ValidationError({"quote_number": "Quote not found."})
        if quote_request.orders.exists():
            raise serializers.ValidationError(
                {"quote_number": "An order has already been created from this quote."}
            )

        attrs["quote_request"] = quote_request
        return attrs

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one product.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        return OrderService.create_order(
            validated_data=validated_data,
            user=getattr(request, "user", None),
        )


class CheckoutSerializer(serializers.ModelSerializer):
    idempotency_key = serializers.UUIDField(write_only=True)
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        write_only=True,
    )
    items = CheckoutItemSerializer(many=True)
    customer_phone = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[validate_phone],
    )

    class Meta:
        model = Order
        fields = (
            "idempotency_key",
            "organization",
            "customer_first_name",
            "customer_last_name",
            "customer_email",
            "customer_phone",
            "company_name",
            "shipping_address",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "notes",
            "items",
        )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one product.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        return OrderService.create_checkout_order(
            validated_data=validated_data,
            user=getattr(request, "user", None),
        )


class OrderStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ("status", "updated_at")
        read_only_fields = ("updated_at",)

    def update(self, instance, validated_data):
        return OrderService.update_status(
            order=instance,
            new_status=validated_data["status"],
        )


class AdminManualOrderItemSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True))
    quantity = serializers.IntegerField(min_value=1, max_value=999)


class AdminManualOrderSerializer(serializers.Serializer):
    customer_mode = serializers.ChoiceField(choices=("existing", "new"))
    customer_id = serializers.IntegerField(required=False, min_value=1)
    customer_first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    customer_last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    customer_email = serializers.EmailField(required=False)
    customer_phone = serializers.CharField(required=False, allow_blank=True, validators=[validate_phone])
    company_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    organization_mode = serializers.ChoiceField(choices=("existing", "new"))
    organization_id = serializers.IntegerField(required=False, min_value=1)
    organization_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    shipping_address = serializers.CharField(required=False, allow_blank=True, max_length=255)
    shipping_city = serializers.CharField(required=False, allow_blank=True, max_length=120)
    shipping_state = serializers.CharField(required=False, allow_blank=True, max_length=120)
    shipping_postal_code = serializers.CharField(required=False, allow_blank=True, max_length=20)
    shipping_country = serializers.CharField(required=False, allow_blank=True, max_length=120)
    shipping_fee = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True)
    payment_state = serializers.ChoiceField(choices=("draft", "waiting_payment", "paid"))
    payment_reference = serializers.CharField(required=False, allow_blank=True, max_length=255)
    items = AdminManualOrderItemSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        if attrs["customer_mode"] == "existing" and not attrs.get("customer_id"):
            raise serializers.ValidationError({"customer_id": "Select a client account."})
        if attrs["customer_mode"] == "new":
            if not attrs.get("customer_email"):
                raise serializers.ValidationError({"customer_email": "Enter the new client's email."})
            if attrs["organization_mode"] != "new":
                raise serializers.ValidationError({
                    "organization_mode": "A newly created client must start with a new organization."
                })
        if attrs["organization_mode"] == "existing" and not attrs.get("organization_id"):
            raise serializers.ValidationError({"organization_id": "Select an organization."})
        if attrs["organization_mode"] == "new" and not attrs.get("organization_name", "").strip():
            raise serializers.ValidationError({"organization_name": "Enter the organization name."})
        if attrs["payment_state"] == "paid" and not attrs.get("payment_reference", "").strip():
            raise serializers.ValidationError({"payment_reference": "Enter the verified payment reference."})
        defaults = {
            "customer_first_name": "",
            "customer_last_name": "",
            "customer_phone": "",
            "company_name": "",
            "shipping_address": "",
            "shipping_city": "",
            "shipping_state": "",
            "shipping_postal_code": "",
            "shipping_country": "",
            "shipping_fee": 0,
            "notes": "",
        }
        for key, value in defaults.items():
            attrs.setdefault(key, value)
        return attrs

    def create(self, validated_data):
        from orders.services import AdminManualOrderService

        return AdminManualOrderService.create(
            validated_data=validated_data,
            actor=self.context["request"].user,
        )
