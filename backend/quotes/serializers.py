from __future__ import annotations

from rest_framework import serializers

from products.models import Product
from quotes.models import QuoteRequest, QuoteRequestItem
from quotes.services import QuoteService
from common.validators import validate_phone


class QuoteRequestItemSerializer(serializers.ModelSerializer):
    product_slug = serializers.CharField(source="product.slug", read_only=True)

    class Meta:
        model = QuoteRequestItem
        fields = (
            "id",
            "product",
            "product_slug",
            "product_name",
            "sku",
            "quantity",
            "specifications",
        )


class QuoteRequestSerializer(serializers.ModelSerializer):
    items = QuoteRequestItemSerializer(many=True, read_only=True)
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = QuoteRequest
        fields = (
            "id",
            "quote_number",
            "status",
            "order_number",
            "requester_company_name",
            "requester_contact_person",
            "requester_email",
            "requester_phone",
            "notes",
            "items",
            "created_at",
            "updated_at",
        )

    def get_order_number(self, obj) -> str:
        order = obj.orders.order_by("created_at", "id").first()
        return order.order_number if order else ""


class QuoteRequestCreateItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.public())

    class Meta:
        model = QuoteRequestItem
        fields = ("product", "quantity", "specifications")
        extra_kwargs = {
            "specifications": {"required": False},
        }

    def validate_quantity(self, value):
        if value > 1000:
            raise serializers.ValidationError("Quantity cannot exceed 1000 units per item.")
        return value


class QuoteRequestCreateSerializer(serializers.ModelSerializer):
    items = QuoteRequestCreateItemSerializer(many=True)
    requester_phone = serializers.CharField(validators=[validate_phone])

    class Meta:
        model = QuoteRequest
        fields = (
            "requester_company_name",
            "requester_contact_person",
            "requester_email",
            "requester_phone",
            "notes",
            "items",
        )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one product.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        return QuoteService.create_quote_request(
            validated_data=validated_data,
            user=getattr(request, "user", None),
        )


class QuoteRequestStatusSerializer(serializers.ModelSerializer):
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = QuoteRequest
        fields = ("status", "order_number")

    def get_order_number(self, obj) -> str:
        order = obj.orders.order_by("created_at", "id").first()
        return order.order_number if order else ""

    def update(self, instance, validated_data):
        request = self.context.get("request")
        return QuoteService.update_status(
            quote_request=instance,
            new_status=validated_data["status"],
            user=getattr(request, "user", None),
        )
