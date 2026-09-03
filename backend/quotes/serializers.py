from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers
from rest_framework.reverse import reverse
from drf_spectacular.utils import extend_schema_field

from common.validators import validate_phone
from products.models import Product
from quotes.models import QuoteMessage, QuoteRequest, QuoteRequestItem
from quotes.services import QuoteService


class QuoteRequestItemSerializer(serializers.ModelSerializer):
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    image_url = serializers.SerializerMethodField()
    suggested_unit_price = serializers.SerializerMethodField()
    bulk_price_applied = serializers.SerializerMethodField()

    class Meta:
        model = QuoteRequestItem
        fields = (
            "id", "product", "product_slug", "product_name", "sku", "quantity",
            "specifications", "quoted_unit_price", "quoted_line_total", "image_url",
            "suggested_unit_price", "bulk_price_applied",
        )

    def get_image_url(self, obj) -> str:
        image = obj.product.images.order_by("-is_primary", "sort_order", "id").first() if obj.product else None
        return image.image_url if image else ""

    def get_bulk_price_applied(self, obj) -> bool:
        product = obj.product
        return bool(
            product
            and product.bulk_minimum_quantity
            and product.bulk_unit_price is not None
            and obj.quantity >= product.bulk_minimum_quantity
        )

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_suggested_unit_price(self, obj) -> Decimal:
        product = obj.product
        if not product:
            return None
        return product.price_for_quantity(obj.quantity)


class QuoteMessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = QuoteMessage
        fields = ("id", "sender_role", "author_name", "body", "created_at")

    def get_author_name(self, obj) -> str:
        if not obj.author:
            return "Digital PTT" if obj.sender_role == QuoteMessage.SenderRole.ADMIN else "Customer"
        return obj.author.get_full_name() or obj.author.email


class QuoteRequestSerializer(serializers.ModelSerializer):
    items = QuoteRequestItemSerializer(many=True, read_only=True)
    messages = QuoteMessageSerializer(many=True, read_only=True)
    order_number = serializers.SerializerMethodField()
    order_status = serializers.SerializerMethodField()
    invoice_pdf_url = serializers.SerializerMethodField()
    renewal_license_number = serializers.CharField(
        source="renewal_license.license_number",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = QuoteRequest
        fields = (
            "id", "quote_number", "status", "order_number", "order_status", "renewal_license_number",
            "requester_company_name", "requester_contact_person", "requester_email",
            "requester_phone", "notes", "admin_message", "quoted_subtotal",
            "quoted_shipping", "quoted_total", "quoted_at", "invoice_number",
            "invoice_pdf_url", "invoiced_at", "payment_rejection_reason",
            "messages", "items", "created_at", "updated_at",
        )

    def get_order_number(self, obj) -> str:
        order = obj.orders.order_by("created_at", "id").first()
        return order.order_number if order else ""

    def get_order_status(self, obj) -> str:
        order = obj.orders.order_by("created_at", "id").first()
        return order.status if order else ""

    def get_invoice_pdf_url(self, obj) -> str:
        if not obj.invoice_pdf:
            return ""
        request = self.context.get("request")
        return reverse(
            "quote-request-invoice-pdf",
            kwargs={"quote_number": obj.quote_number},
            request=request,
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not getattr(user, "is_staff", False) and not instance.quoted_at:
            data.update({
                "admin_message": "",
                "quoted_subtotal": None,
                "quoted_total": None,
            })
            for item in data["items"]:
                item["quoted_unit_price"] = None
                item["quoted_line_total"] = None
        if instance.status != QuoteRequest.Status.PAYMENT_REJECTED:
            data["payment_rejection_reason"] = ""
        return data

class QuoteRequestCreateItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.public())

    class Meta:
        model = QuoteRequestItem
        fields = ("product", "quantity", "specifications")
        extra_kwargs = {"specifications": {"required": False}}

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
            "requester_company_name", "requester_contact_person", "requester_email",
            "requester_phone", "notes", "items",
        )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one product.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if (
            user
            and user.is_authenticated
            and not user.is_staff
            and attrs["requester_email"].lower() != user.email.lower()
        ):
            raise serializers.ValidationError({
                "requester_email": "Use the email address on your signed-in account."
            })
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        return QuoteService.create_quote_request(
            validated_data=validated_data,
            user=getattr(request, "user", None),
        )


class QuoteClaimSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True)

    def save(self, **kwargs):
        return QuoteService.claim_guest_quote(
            quote_request=self.context["quote_request"],
            user=self.context["request"].user,
            token=self.validated_data["token"],
        )


class QuotePricingItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    quoted_unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )


class QuoteRequestStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteRequest
        fields = ("status",)

    def validate_status(self, value):
        if value in {
            QuoteRequest.Status.INVOICE_SENT,
            QuoteRequest.Status.AWAITING_PAYMENT,
            QuoteRequest.Status.PAYMENT_CONFIRMED,
            QuoteRequest.Status.PAYMENT_REJECTED,
        }:
            raise serializers.ValidationError("Use the invoice workflow for this status.")
        return value

    def update(self, instance, validated_data):
        request = self.context.get("request")
        return QuoteService.update_status(
            quote_request=instance,
            new_status=validated_data["status"],
            user=getattr(request, "user", None),
        )


class QuoteInvoiceSerializer(serializers.Serializer):
    items = QuotePricingItemSerializer(many=True)
    quoted_shipping = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00")
    )
    admin_message = serializers.CharField(required=False, allow_blank=True)

    def save(self, **kwargs):
        request = self.context["request"]
        return QuoteService.issue_invoice(
            quote_request=self.context["quote_request"],
            user=request.user,
            item_prices=self.validated_data["items"],
            shipping=self.validated_data["quoted_shipping"],
            admin_message=self.validated_data.get("admin_message", ""),
        )


class QuoteMessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000, allow_blank=False, trim_whitespace=True)

    def save(self, **kwargs):
        return QuoteService.add_message(
            quote_request=self.context["quote_request"],
            user=self.context["request"].user,
            body=self.validated_data["body"],
        )
