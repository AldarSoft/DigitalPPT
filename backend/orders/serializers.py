from __future__ import annotations

from rest_framework import serializers
from quotes.models import QuoteRequest

from orders.models import Order, OrderItem
from orders.services import OrderService
from common.validators import validate_phone
from products.models import Product


class OrderItemSerializer(serializers.ModelSerializer):
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    image_url = serializers.SerializerMethodField()

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
            "line_total",
            "image_url",
        )

    def get_image_url(self, obj) -> str:
        image = obj.product.images.order_by("-is_primary", "sort_order", "id").first() if obj.product else None
        return image.image_url if image else ""


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    quote_number = serializers.CharField(source="quote_request.quote_number", read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "quote_number",
            "user_id",
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
            "total",
            "stock_deducted",
            "notes",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("stock_deducted",)


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


class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderCreateItemSerializer(many=True)
    quote_number = serializers.CharField(write_only=True, required=False)
    customer_phone = serializers.CharField(required=False, allow_blank=True, validators=[validate_phone])

    class Meta:
        model = Order
        fields = (
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
    items = CheckoutItemSerializer(many=True)
    customer_phone = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[validate_phone],
    )

    class Meta:
        model = Order
        fields = (
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
        inventory_errors = {}
        for item in value:
            product = item["product"]
            if product.inventory_quantity < item["quantity"]:
                inventory_errors[str(product.pk)] = (
                    f"Only {product.inventory_quantity} units are available."
                )
        if inventory_errors:
            raise serializers.ValidationError(inventory_errors)
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
        fields = ("status",)

    def update(self, instance, validated_data):
        return OrderService.update_status(
            order=instance,
            new_status=validated_data["status"],
        )
