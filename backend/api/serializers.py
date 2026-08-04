from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from .models import (
    Banner,
    Category,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductSpecification,
    QuoteRequest,
    QuoteRequestItem,
    SiteSettings,
    Testimonial,
    UserProfile,
)


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.URLField(source="image_url")
    isPrimary = serializers.BooleanField(source="is_primary")

    class Meta:
        model = ProductImage
        fields = ["id", "url", "alt", "isPrimary"]


class ProductSpecificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSpecification
        fields = ["name", "value"]


class CategorySerializer(serializers.ModelSerializer):
    parentId = serializers.IntegerField(source="parent_id", allow_null=True, read_only=True)
    productCount = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "image",
            "parentId",
            "productCount",
        ]

    def get_productCount(self, obj):
        # Expose the number of products so admin and catalog UIs can show category totals directly.
        return obj.products.count()


class CategoryWriteSerializer(serializers.ModelSerializer):
    parentId = serializers.PrimaryKeyRelatedField(
        source="parent",
        queryset=Category.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Category
        fields = ["name", "slug", "description", "image", "parentId"]


class ProductSerializer(serializers.ModelSerializer):
    shortDescription = serializers.CharField(source="short_description")
    salePrice = serializers.DecimalField(
        source="sale_price", max_digits=12, decimal_places=2, allow_null=True
    )
    costPrice = serializers.DecimalField(
        source="cost_price", max_digits=12, decimal_places=2, allow_null=True
    )
    categoryId = serializers.IntegerField(source="category_id")
    categoryName = serializers.CharField(source="category.name")
    reviewCount = serializers.IntegerField(source="review_count")
    isFeatured = serializers.BooleanField(source="is_featured")
    isBestSeller = serializers.BooleanField(source="is_best_seller")
    isNew = serializers.BooleanField(source="is_new")
    createdAt = serializers.SerializerMethodField()
    updatedAt = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)
    specifications = ProductSpecificationSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "description",
            "shortDescription",
            "price",
            "salePrice",
            "costPrice",
            "stock",
            "unit",
            "categoryId",
            "categoryName",
            "brand",
            "images",
            "specifications",
            "tags",
            "rating",
            "reviewCount",
            "isFeatured",
            "isBestSeller",
            "isNew",
            "createdAt",
            "updatedAt",
        ]

    def get_createdAt(self, obj):
        # Match the frontend mock contract, which expects a plain ISO date string.
        return obj.created_at.date().isoformat()

    def get_updatedAt(self, obj):
        # Match the frontend mock contract, which expects a plain ISO date string.
        return obj.updated_at.date().isoformat()


class ProductWriteSerializer(serializers.ModelSerializer):
    shortDescription = serializers.CharField(
        source="short_description", allow_blank=True, required=False
    )
    salePrice = serializers.DecimalField(
        source="sale_price",
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        required=False,
    )
    costPrice = serializers.DecimalField(
        source="cost_price",
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        required=False,
    )
    categoryId = serializers.PrimaryKeyRelatedField(source="category", queryset=Category.objects.all())
    reviewCount = serializers.IntegerField(source="review_count", required=False)
    isFeatured = serializers.BooleanField(source="is_featured", required=False)
    isBestSeller = serializers.BooleanField(source="is_best_seller", required=False)
    isNew = serializers.BooleanField(source="is_new", required=False)

    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "sku",
            "description",
            "shortDescription",
            "price",
            "salePrice",
            "costPrice",
            "stock",
            "unit",
            "categoryId",
            "brand",
            "tags",
            "rating",
            "reviewCount",
            "isFeatured",
            "isBestSeller",
            "isNew",
        ]

    def validate_slug(self, value):
        # Normalize manual slug input so stored URLs stay consistent.
        return slugify(value) if value else value

    def create(self, validated_data):
        # Fill in frontend-friendly defaults when admin forms omit optional product fields.
        if not validated_data.get("slug"):
            validated_data["slug"] = slugify(validated_data["name"])
        validated_data.setdefault("unit", "unit")
        validated_data.setdefault("tags", [])
        return super().create(validated_data)


class UserSerializer(serializers.ModelSerializer):
    firstName = serializers.CharField(source="first_name")
    lastName = serializers.CharField(source="last_name")
    phone = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    createdAt = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "firstName",
            "lastName",
            "email",
            "phone",
            "company",
            "role",
            "avatar",
            "createdAt",
        ]

    def _profile(self, obj):
        # Keep profile lookups in one place because several response fields depend on it.
        return getattr(obj, "profile", None)

    def get_phone(self, obj):
        # Flatten profile data into the user payload expected by the frontend.
        profile = self._profile(obj)
        return profile.phone if profile else ""

    def get_company(self, obj):
        # Flatten profile data into the user payload expected by the frontend.
        profile = self._profile(obj)
        return profile.company if profile else ""

    def get_role(self, obj):
        # Default to customer when a profile has not been created yet.
        profile = self._profile(obj)
        return profile.role if profile else UserProfile.Role.CUSTOMER

    def get_avatar(self, obj):
        # Flatten profile data into the user payload expected by the frontend.
        profile = self._profile(obj)
        return profile.avatar if profile else ""

    def get_createdAt(self, obj):
        # Match the frontend mock contract, which expects a plain ISO date string.
        return obj.date_joined.date().isoformat()


class RegisterSerializer(serializers.Serializer):
    firstName = serializers.CharField(max_length=150)
    lastName = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=100, required=False, allow_blank=True)
    company = serializers.CharField(max_length=255, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_email(self, value):
        # Stop duplicate registrations before we create both the user and profile records.
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already exists.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        # Create the auth user and the linked customer profile as one atomic registration flow.
        email = validated_data["email"].lower()
        user = User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
            first_name=validated_data["firstName"],
            last_name=validated_data["lastName"],
        )
        UserProfile.objects.create(
            user=user,
            phone=validated_data.get("phone", ""),
            company=validated_data.get("company", ""),
            role=UserProfile.Role.CUSTOMER,
        )
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        # Authenticate using the email-backed username created during registration.
        email = attrs["email"].lower()
        user = authenticate(
            request=self.context.get("request"),
            username=email,
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        attrs["user"] = user
        return attrs


class AdminWriteSerializer(serializers.Serializer):
    firstName = serializers.CharField(max_length=150)
    lastName = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=100, required=False, allow_blank=True)
    company = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_email(self, value):
        # Reuse the same uniqueness rule for both admin creation and admin edits.
        instance = self.context.get("instance")
        existing = User.objects.filter(email__iexact=value)
        if instance:
            existing = existing.exclude(pk=instance.pk)
        if existing.exists():
            raise serializers.ValidationError("Email already exists.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        # Create an admin-capable auth user and the matching admin profile together.
        email = validated_data["email"].lower()
        user = User.objects.create_user(
            username=email,
            email=email,
            password=User.objects.make_random_password(),
            first_name=validated_data["firstName"],
            last_name=validated_data["lastName"],
            is_staff=True,
        )
        UserProfile.objects.create(
            user=user,
            phone=validated_data.get("phone", ""),
            company=validated_data.get("company", ""),
            role=UserProfile.Role.ADMIN,
        )
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        # Keep the Django user record and custom admin profile in sync during edits.
        email = validated_data["email"].lower()
        instance.username = email
        instance.email = email
        instance.first_name = validated_data["firstName"]
        instance.last_name = validated_data["lastName"]
        instance.is_staff = True
        instance.save()
        profile, _ = UserProfile.objects.get_or_create(user=instance)
        profile.phone = validated_data.get("phone", "")
        profile.company = validated_data.get("company", "")
        profile.role = UserProfile.Role.ADMIN
        profile.save()
        return instance


class OrderItemSerializer(serializers.ModelSerializer):
    productId = serializers.IntegerField(source="product_id", allow_null=True)

    class Meta:
        model = OrderItem
        fields = ["productId", "name", "image", "price", "quantity", "sku"]


class OrderSerializer(serializers.ModelSerializer):
    orderNumber = serializers.CharField(source="order_number")
    createdAt = serializers.DateTimeField(source="created_at")
    updatedAt = serializers.DateTimeField(source="updated_at")
    items = OrderItemSerializer(many=True)
    customer = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()
    delivery = serializers.SerializerMethodField()
    orderNotes = serializers.CharField(source="order_notes")

    class Meta:
        model = Order
        fields = [
            "id",
            "orderNumber",
            "status",
            "customer",
            "company",
            "delivery",
            "items",
            "subtotal",
            "shipping",
            "tax",
            "total",
            "orderNotes",
            "createdAt",
            "updatedAt",
        ]

    def get_customer(self, obj):
        # Reshape flat model fields into the nested customer object used by the frontend.
        return {
            "firstName": obj.customer_first_name,
            "lastName": obj.customer_last_name,
            "email": obj.customer_email,
            "phone": obj.customer_phone,
        }

    def get_company(self, obj):
        # Reshape flat model fields into the nested company object used by the frontend.
        return {
            "companyName": obj.company_name,
            "taxId": obj.tax_id,
            "industry": obj.industry,
        }

    def get_delivery(self, obj):
        # Reshape flat model fields into the nested delivery object used by the frontend.
        return {
            "address": obj.delivery_address,
            "city": obj.delivery_city,
            "state": obj.delivery_state,
            "zipCode": obj.delivery_zip_code,
            "country": obj.delivery_country,
        }


class QuoteRequestItemSerializer(serializers.ModelSerializer):
    productId = serializers.IntegerField(source="product_id", allow_null=True)
    categoryName = serializers.CharField(source="category_name")
    invoiceRequested = serializers.BooleanField(source="invoice_requested")

    class Meta:
        model = QuoteRequestItem
        fields = [
            "productId",
            "name",
            "sku",
            "categoryName",
            "quantity",
            "specifications",
            "invoiceRequested",
        ]


class QuoteRequestSerializer(serializers.ModelSerializer):
    quoteNumber = serializers.CharField(source="quote_number")
    createdAt = serializers.DateTimeField(source="created_at")
    updatedAt = serializers.DateTimeField(source="updated_at")
    requester = serializers.SerializerMethodField()
    items = QuoteRequestItemSerializer(many=True)

    class Meta:
        model = QuoteRequest
        fields = [
            "id",
            "quoteNumber",
            "status",
            "requester",
            "items",
            "createdAt",
            "updatedAt",
        ]

    def get_requester(self, obj):
        # Reshape requester fields into the nested object already used in the quote screens.
        return {
            "companyName": obj.requester_company_name,
            "contactPerson": obj.requester_contact_person,
            "email": obj.requester_email,
            "phone": obj.requester_phone,
            "notes": obj.requester_notes,
        }


class QuoteRequestCreateSerializer(serializers.Serializer):
    requester = serializers.DictField()
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)

    def validate_requester(self, value):
        # Enforce the minimum requester fields required by the quote request form.
        required = ["companyName", "contactPerson", "email", "phone"]
        missing = [field for field in required if not value.get(field)]
        if missing:
            raise serializers.ValidationError(
                f"Missing requester fields: {', '.join(missing)}"
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        # Persist the quote and all requested items together so partial quote writes cannot occur.
        requester = validated_data["requester"]
        quote = QuoteRequest.objects.create(
            requester_company_name=requester["companyName"],
            requester_contact_person=requester["contactPerson"],
            requester_email=requester["email"],
            requester_phone=requester["phone"],
            requester_notes=requester.get("notes", ""),
        )
        for item in validated_data["items"]:
            QuoteRequestItem.objects.create(
                quote_request=quote,
                product_id=item.get("productId"),
                name=item["name"],
                sku=item.get("sku", ""),
                category_name=item.get("categoryName", ""),
                quantity=item.get("quantity", 1),
                specifications=item.get("specifications", []),
                invoice_requested=item.get("invoiceRequested", False),
            )
        return quote


class BannerSerializer(serializers.ModelSerializer):
    subtitle = serializers.CharField(allow_blank=True, required=False)
    ctaText = serializers.CharField(source="cta_text", allow_blank=True, required=False)
    ctaLink = serializers.CharField(source="cta_link", allow_blank=True, required=False)
    isActive = serializers.BooleanField(source="is_active", required=False)
    sortOrder = serializers.IntegerField(source="sort_order", required=False)

    class Meta:
        model = Banner
        fields = [
            "id",
            "title",
            "subtitle",
            "description",
            "ctaText",
            "ctaLink",
            "image",
            "isActive",
            "sortOrder",
        ]


class TestimonialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Testimonial
        fields = ["id", "name", "company", "role", "avatar", "content", "rating"]


class SiteSettingsSerializer(serializers.ModelSerializer):
    contact = serializers.SerializerMethodField()
    siteName = serializers.CharField(source="site_name")
    taxRate = serializers.CharField(source="tax_rate")
    shippingRate = serializers.DecimalField(source="shipping_rate", max_digits=12, decimal_places=2)
    freeShippingMin = serializers.DecimalField(source="free_shipping_min", max_digits=12, decimal_places=2)

    class Meta:
        model = SiteSettings
        fields = [
            "siteName",
            "tagline",
            "contact",
            "currency",
            "taxRate",
            "shippingRate",
            "freeShippingMin",
        ]

    def get_contact(self, obj):
        # Group contact fields so the response matches the frontend settings shape.
        return {
            "email": obj.contact_email,
            "phone": obj.contact_phone,
            "address": obj.contact_address,
            "workingHours": obj.working_hours,
        }


class AdminSiteSettingsSerializer(SiteSettingsSerializer):
    smtpHost = serializers.CharField(source="smtp_host")
    smtpPort = serializers.CharField(source="smtp_port")
    smtpUser = serializers.CharField(source="smtp_user")
    smtpPass = serializers.CharField(source="smtp_password")
    fromEmail = serializers.CharField(source="from_email")

    class Meta(SiteSettingsSerializer.Meta):
        fields = SiteSettingsSerializer.Meta.fields + [
            "smtpHost",
            "smtpPort",
            "smtpUser",
            "smtpPass",
            "fromEmail",
        ]


class SiteSettingsWriteSerializer(serializers.ModelSerializer):
    siteName = serializers.CharField(source="site_name", required=False)
    taxRate = serializers.CharField(source="tax_rate", required=False, allow_blank=True)
    shippingRate = serializers.DecimalField(
        source="shipping_rate", max_digits=12, decimal_places=2, required=False
    )
    freeShippingMin = serializers.DecimalField(
        source="free_shipping_min", max_digits=12, decimal_places=2, required=False
    )
    smtpHost = serializers.CharField(source="smtp_host", required=False, allow_blank=True)
    smtpPort = serializers.CharField(source="smtp_port", required=False, allow_blank=True)
    smtpUser = serializers.CharField(source="smtp_user", required=False, allow_blank=True)
    smtpPass = serializers.CharField(source="smtp_password", required=False, allow_blank=True)
    fromEmail = serializers.EmailField(source="from_email", required=False, allow_blank=True)
    contact = serializers.DictField(required=False)

    class Meta:
        model = SiteSettings
        fields = [
            "siteName",
            "tagline",
            "currency",
            "taxRate",
            "shippingRate",
            "freeShippingMin",
            "smtpHost",
            "smtpPort",
            "smtpUser",
            "smtpPass",
            "fromEmail",
            "contact",
        ]

    def update(self, instance, validated_data):
        # Support partial admin updates while still unpacking the nested contact payload cleanly.
        contact = validated_data.pop("contact", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if contact:
            instance.contact_email = contact.get("email", instance.contact_email)
            instance.contact_phone = contact.get("phone", instance.contact_phone)
            instance.contact_address = contact.get("address", instance.contact_address)
            instance.working_hours = contact.get(
                "workingHours", instance.working_hours
            )
        instance.save()
        return instance
