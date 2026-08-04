from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils.text import slugify


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimestampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    image = models.URLField(blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TimestampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    sku = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    short_description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    stock = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=50, default="unit")
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    brand = models.CharField(max_length=255, blank=True)
    tags = models.JSONField(default=list, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal("0.0"))
    review_count = models.PositiveIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    is_best_seller = models.BooleanField(default=False)
    is_new = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "name"]

    def save(self, *args, **kwargs):
        # Auto-generate a URL slug when the product is created without one.
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image_url = models.URLField()
    alt = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.name} image {self.id}"


class ProductSpecification(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="specifications"
    )
    name = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class UserProfile(TimestampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        CUSTOMER = "customer", "Customer"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=100, blank=True)
    company = models.CharField(max_length=255, blank=True)
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.CUSTOMER
    )
    avatar = models.URLField(blank=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Order(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    order_number = models.CharField(max_length=40, unique=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    customer_first_name = models.CharField(max_length=150)
    customer_last_name = models.CharField(max_length=150)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=100, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=120, blank=True)
    industry = models.CharField(max_length=120, blank=True)
    delivery_address = models.CharField(max_length=255)
    delivery_city = models.CharField(max_length=120)
    delivery_state = models.CharField(max_length=120, blank=True)
    delivery_zip_code = models.CharField(max_length=40, blank=True)
    delivery_country = models.CharField(max_length=120)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    order_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        # Save first so the order gets a primary key, then derive the human-readable order number.
        super().save(*args, **kwargs)
        if not self.order_number:
            self.order_number = f"ORD-{self.created_at.year}-{self.pk:04d}"
            super().save(update_fields=["order_number"])

    def __str__(self):
        return self.order_number or f"Order {self.pk}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    name = models.CharField(max_length=255)
    image = models.URLField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    sku = models.CharField(max_length=120)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.order} - {self.name}"


class QuoteRequest(TimestampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUOTED = "quoted", "Quoted"
        CLOSED = "closed", "Closed"

    quote_number = models.CharField(max_length=40, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    requester_company_name = models.CharField(max_length=255)
    requester_contact_person = models.CharField(max_length=255)
    requester_email = models.EmailField()
    requester_phone = models.CharField(max_length=100)
    requester_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        # Save first so the quote gets a primary key, then derive the human-readable quote number.
        super().save(*args, **kwargs)
        if not self.quote_number:
            self.quote_number = f"QTE-{self.created_at.year}-{self.pk:04d}"
            super().save(update_fields=["quote_number"])

    def __str__(self):
        return self.quote_number or f"Quote {self.pk}"


class QuoteRequestItem(models.Model):
    quote_request = models.ForeignKey(
        QuoteRequest, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True)
    category_name = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    specifications = models.JSONField(default=list, blank=True)
    invoice_requested = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quote_request} - {self.name}"


class Banner(TimestampedModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    cta_text = models.CharField(max_length=120, blank=True)
    cta_link = models.CharField(max_length=255, blank=True)
    image = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title


class Testimonial(TimestampedModel):
    name = models.CharField(max_length=255)
    company = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=255, blank=True)
    avatar = models.URLField(blank=True)
    content = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class SiteSettings(TimestampedModel):
    site_name = models.CharField(max_length=255, default="Rack & Bracket")
    tagline = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=100, blank=True)
    contact_address = models.TextField(blank=True)
    working_hours = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=20, default="USD")
    tax_rate = models.CharField(max_length=50, blank=True)
    shipping_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    free_shipping_min = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.CharField(max_length=20, blank=True)
    smtp_user = models.CharField(max_length=255, blank=True)
    smtp_password = models.CharField(max_length=255, blank=True)
    from_email = models.EmailField(blank=True)

    class Meta:
        verbose_name_plural = "site settings"

    def __str__(self):
        return self.site_name
