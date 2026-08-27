from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from common.models import ActiveModel, TimeStampedModel


class Category(ActiveModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255, blank=True)
    description = models.TextField(blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        indexes = [
            models.Index(fields=["slug", "is_active"]),
            models.Index(fields=["name", "is_active"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Category.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def with_catalog_relations(self):
        return self.select_related("category", "required_license_product").prefetch_related(
            "images", "specifications"
        )

    def public(self):
        return self.filter(
            is_active=True,
            status=Product.Status.PUBLISHED,
            category__is_active=True,
        )


class Product(ActiveModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class LicensingRole(models.TextChoices):
        STANDARD = "standard", "Standard product"
        LICENSED_PRODUCT = "licensed_product", "Licensed product"
        LICENSE_PRODUCT = "license_product", "License product"

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255, blank=True)
    sku = models.CharField(max_length=120, unique=True)
    brand = models.CharField(max_length=255, blank=True)
    short_description = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    bulk_minimum_quantity = models.PositiveIntegerField(null=True, blank=True)
    bulk_unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    inventory_quantity = models.PositiveIntegerField(default=0)
    licensing_role = models.CharField(
        max_length=24,
        choices=LicensingRole.choices,
        default=LicensingRole.STANDARD,
        db_index=True,
    )
    required_license_product = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="compatible_products",
    )
    license_capacity = models.PositiveIntegerField(null=True, blank=True)
    license_term_days = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    is_featured = models.BooleanField(default=False, db_index=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "name")
        verbose_name = "Product"
        verbose_name_plural = "Products"
        indexes = [
            models.Index(fields=["category", "status", "is_active"]),
            models.Index(fields=["sku"]),
            models.Index(fields=["is_featured", "status"]),
            models.Index(fields=["brand"]),
            models.Index(fields=["licensing_role", "status", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        licensing_role="standard",
                        required_license_product__isnull=True,
                        license_capacity__isnull=True,
                        license_term_days__isnull=True,
                    )
                    | Q(
                        licensing_role="licensed_product",
                        required_license_product__isnull=False,
                        license_capacity__isnull=True,
                        license_term_days__isnull=True,
                    )
                    | Q(
                        licensing_role="license_product",
                        required_license_product__isnull=True,
                        license_capacity__isnull=False,
                        license_term_days__isnull=False,
                    )
                ),
                name="products_licensing_metadata_by_role",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.required_license_product_id == self.pk and self.pk is not None:
            errors["required_license_product"] = "A product cannot require itself."

        if self.licensing_role == self.LicensingRole.LICENSED_PRODUCT:
            if not self.required_license_product_id:
                errors["required_license_product"] = (
                    "Select the license product consumed by this product."
                )
            elif (
                self.required_license_product
                and self.required_license_product.licensing_role
                != self.LicensingRole.LICENSE_PRODUCT
            ):
                errors["required_license_product"] = (
                    "The compatible product must be a license product."
                )
        elif self.licensing_role == self.LicensingRole.LICENSE_PRODUCT:
            if not self.license_capacity:
                errors["license_capacity"] = "License capacity must be greater than zero."
            if not self.license_term_days:
                errors["license_term_days"] = "License term must be greater than zero."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or self.sku.lower()
            slug = base_slug
            counter = 1
            while Product.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def current_price(self):
        return self.sale_price or self.price

    def price_for_quantity(self, quantity):
        if (
            self.bulk_minimum_quantity
            and self.bulk_unit_price is not None
            and quantity >= self.bulk_minimum_quantity
        ):
            return self.bulk_unit_price
        return self.current_price

    @property
    def is_stock_tracked(self):
        return self.licensing_role != self.LicensingRole.LICENSE_PRODUCT

    def __str__(self):
        return self.name


class InventoryAdjustment(TimeStampedModel):
    class Mode(models.TextChoices):
        ADD = "add", "Add stock"
        SET = "set", "Set counted quantity"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="inventory_adjustments",
    )
    performed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventory_adjustments",
    )
    mode = models.CharField(max_length=12, choices=Mode.choices)
    quantity = models.PositiveIntegerField()
    quantity_before = models.PositiveIntegerField()
    quantity_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=64)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["product", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.product} {self.mode} {self.quantity}"


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image_url = models.CharField(max_length=500)
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Product Image"
        verbose_name_plural = "Product Images"
        indexes = [
            models.Index(fields=["product", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.product.name} image"


class ProductSpecification(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="specifications",
    )
    key = models.CharField(max_length=120)
    value = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Product Specification"
        verbose_name_plural = "Product Specifications"
        indexes = [
            models.Index(fields=["product", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.key}"
