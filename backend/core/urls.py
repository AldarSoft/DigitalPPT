from django.urls import path
from rest_framework.routers import DefaultRouter

from core.views import BannerViewSet, ContactMessageCreateView, PromotionViewSet, SiteSettingView

router = DefaultRouter()
router.register("banners", BannerViewSet, basename="banner")
router.register("promotions", PromotionViewSet, basename="promotion")

urlpatterns = [
    path("site-settings/", SiteSettingView.as_view(), name="site-settings"),
    path("contact-messages/", ContactMessageCreateView.as_view(), name="contact-message-create"),
]
urlpatterns += router.urls
