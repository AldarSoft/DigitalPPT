from __future__ import annotations

from django.db import models
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
        return self.select_related("category").prefetch_related("images", "specifications")

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
    inventory_quantity = models.PositiveIntegerField(default=0)
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
        ]

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

    def __str__(self):
        return self.name


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
