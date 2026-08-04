from django.contrib import admin

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

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(ProductImage)
admin.site.register(ProductSpecification)
admin.site.register(UserProfile)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(QuoteRequest)
admin.site.register(QuoteRequestItem)
admin.site.register(Banner)
admin.site.register(Testimonial)
admin.site.register(SiteSettings)
