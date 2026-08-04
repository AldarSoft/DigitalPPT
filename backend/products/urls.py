from rest_framework.routers import DefaultRouter
from django.urls import path

from products.views import CategoryViewSet, ProductImageUploadView, ProductViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("catalog", ProductViewSet, basename="product")

urlpatterns = [
    path("upload-image/", ProductImageUploadView.as_view(), name="product-image-upload"),
    *router.urls,
]
