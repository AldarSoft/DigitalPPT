from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from products.models import Category, Product, ProductImage, ProductSpecification


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "image_url",
            "parent",
            "is_active",
            "product_count",
        )

    def get_product_count(self, obj) -> int:
        request = self.context.get("request")
        if request and request.user and request.user.is_staff:
            return obj.products.count()
        return Product.objects.public().filter(category=obj).count()


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image_url", "alt_text", "is_primary", "sort_order")


class ProductSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpecification
        fields = ("id", "key", "value", "sort_order")


class LicenseProductSummarySerializer(serializers.ModelSerializer):
    current_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "current_price",
            "license_capacity",
            "license_term_days",
        )

    def get_current_price(self, obj) -> Decimal:
        return obj.current_price


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    specifications = ProductSpecificationSerializer(many=True, read_only=True)
    current_price = serializers.SerializerMethodField()
    inventory_quantity = serializers.SerializerMethodField()
    on_hand_inventory_quantity = serializers.IntegerField(source="inventory_quantity", read_only=True)
    reserved_inventory_quantity = serializers.SerializerMethodField()
    required_license_product = LicenseProductSummarySerializer(read_only=True)
    is_stock_tracked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "brand",
            "short_description",
            "description",
            "price",
            "sale_price",
            "bulk_minimum_quantity",
            "bulk_unit_price",
            "current_price",
            "inventory_quantity",
            "on_hand_inventory_quantity",
            "reserved_inventory_quantity",
            "licensing_role",
            "required_license_product",
            "license_capacity",
            "license_term_days",
            "is_stock_tracked",
            "status",
            "is_featured",
            "is_active",
            "category",
            "images",
            "specifications",
            "created_at",
            "updated_at",
        )

    def get_current_price(self, obj) -> Decimal:
        return obj.current_price

    def get_inventory_quantity(self, obj) -> int:
        return max(0, getattr(obj, "sellable_inventory_quantity", obj.inventory_quantity))

    def get_reserved_inventory_quantity(self, obj) -> int:
        return max(0, getattr(obj, "reserved_inventory_quantity", 0))


class AdminProductSerializer(ProductSerializer):
    class Meta(ProductSerializer.Meta):
        fields = (
            *ProductSerializer.Meta.fields[:9],
            "cost_price",
            *ProductSerializer.Meta.fields[9:],
        )


class ProductImageUploadRequestSerializer(serializers.Serializer):
    image = serializers.ImageField()


class ProductImageUploadResponseSerializer(serializers.Serializer):
    image_url = serializers.CharField()


class CategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "name",
            "slug",
            "description",
            "image_url",
            "parent",
            "is_active",
        )


class ProductWriteSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, required=False)
    specifications = ProductSpecificationSerializer(many=True, required=False)
    required_license_product_id = serializers.PrimaryKeyRelatedField(
        source="required_license_product",
        queryset=Product.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = Product
        fields = (
            "category",
            "name",
            "slug",
            "sku",
            "brand",
            "short_description",
            "description",
            "price",
            "cost_price",
            "sale_price",
            "bulk_minimum_quantity",
            "bulk_unit_price",
            "inventory_quantity",
            "licensing_role",
            "required_license_product_id",
            "license_capacity",
            "license_term_days",
            "status",
            "is_featured",
            "is_active",
            "images",
            "specifications",
        )

    def validate(self, attrs):
        price = attrs.get("price", getattr(self.instance, "price", None))
        cost_price = attrs.get("cost_price", getattr(self.instance, "cost_price", None))
        sale_price = attrs.get("sale_price", getattr(self.instance, "sale_price", None))
        errors = {}
        if price is not None and price < 0:
            errors["price"] = "Price cannot be negative."
        if cost_price is not None and cost_price < 0:
            errors["cost_price"] = "Cost price cannot be negative."
        if sale_price is not None and sale_price < 0:
            errors["sale_price"] = "Sale price cannot be negative."
        bulk_minimum_quantity = attrs.get(
            "bulk_minimum_quantity", getattr(self.instance, "bulk_minimum_quantity", None)
        )
        bulk_unit_price = attrs.get(
            "bulk_unit_price", getattr(self.instance, "bulk_unit_price", None)
        )
        if (bulk_minimum_quantity is None) != (bulk_unit_price is None):
            errors["bulk_unit_price"] = "Set both a bulk quantity and bulk unit price."
        if bulk_minimum_quantity is not None and bulk_minimum_quantity < 2:
            errors["bulk_minimum_quantity"] = "Bulk quantity must be at least 2."
        effective_price = sale_price if sale_price is not None else price
        if bulk_unit_price is not None and bulk_unit_price <= 0:
            errors["bulk_unit_price"] = "Bulk unit price must be greater than zero."
        if effective_price is not None and bulk_unit_price is not None and bulk_unit_price > effective_price:
            errors["bulk_unit_price"] = "Bulk unit price cannot exceed the current unit price."
        if price is not None and sale_price is not None and sale_price > price:
            errors["sale_price"] = "Sale price cannot be greater than the regular price."
        licensing_role = attrs.get(
            "licensing_role", getattr(self.instance, "licensing_role", Product.LicensingRole.STANDARD)
        )
        required_license_product = attrs.get(
            "required_license_product",
            getattr(self.instance, "required_license_product", None),
        )
        license_capacity = attrs.get(
            "license_capacity", getattr(self.instance, "license_capacity", None)
        )
        license_term_days = attrs.get(
            "license_term_days", getattr(self.instance, "license_term_days", None)
        )
        if licensing_role == Product.LicensingRole.STANDARD:
            if required_license_product or license_capacity or license_term_days:
                errors["licensing_role"] = (
                    "Standard products cannot contain license compatibility metadata."
                )
        elif licensing_role == Product.LicensingRole.LICENSED_PRODUCT:
            if not required_license_product:
                errors["required_license_product_id"] = (
                    "Select the license product consumed by this product."
                )
            elif required_license_product.licensing_role != Product.LicensingRole.LICENSE_PRODUCT:
                errors["required_license_product_id"] = (
                    "The compatible product must be a license product."
                )
            if license_capacity or license_term_days:
                errors["licensing_role"] = (
                    "Licensed products consume capacity; they do not supply it."
                )
        elif licensing_role == Product.LicensingRole.LICENSE_PRODUCT:
            if required_license_product:
                errors["required_license_product_id"] = (
                    "A license product cannot require another license product."
                )
            if not license_capacity:
                errors["license_capacity"] = "License capacity must be greater than zero."
            if not license_term_days:
                errors["license_term_days"] = "License term must be greater than zero."
        if self.instance and required_license_product == self.instance:
            errors["required_license_product_id"] = "A product cannot require itself."
        images = attrs.get("images")
        if images is not None and sum(bool(image.get("is_primary")) for image in images) > 1:
            errors["images"] = "Only one product image can be primary."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        specifications_data = validated_data.pop("specifications", [])
        product = Product.objects.create(**validated_data)
        self._sync_children(product, images_data, specifications_data)
        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        specifications_data = validated_data.pop("specifications", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if images_data is not None or specifications_data is not None:
            self._sync_children(instance, images_data, specifications_data)
        return instance

    def _sync_children(self, product, images_data, specifications_data):
        if images_data is not None:
            product.images.all().delete()
            if images_data and not any(image.get("is_primary") for image in images_data):
                images_data[0]["is_primary"] = True
            ProductImage.objects.bulk_create(
                [ProductImage(product=product, **image) for image in images_data]
            )
        if specifications_data is not None:
            product.specifications.all().delete()
            ProductSpecification.objects.bulk_create(
                [
                    ProductSpecification(product=product, **specification)
                    for specification in specifications_data
                ]
            )
