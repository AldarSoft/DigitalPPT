from django.contrib import admin

from products.models import Category, Product, ProductImage, ProductSpecification


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "image_url", "is_active", "created_at")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline, ProductSpecificationInline]
    list_display = (
        "name",
        "sku",
        "category",
        "status",
        "price",
        "cost_price",
        "sale_price",
        "inventory_quantity",
        "is_featured",
        "is_active",
    )
    list_filter = ("status", "is_featured", "is_active", "category")
    search_fields = ("name", "slug", "sku", "brand")
    list_select_related = ("category",)
    prepopulated_fields = {"slug": ("name",)}
