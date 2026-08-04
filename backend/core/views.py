from django.core.cache import cache
from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from common.permissions import IsAdminOrReadOnly
from core.models import Banner, ContactMessage, Promotion, SiteSetting
from core.serializers import (
    BannerSerializer,
    ContactMessageSerializer,
    PromotionSerializer,
    SiteSettingSerializer,
)


class BannerViewSet(viewsets.ModelViewSet):
    serializer_class = BannerSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ("title", "subtitle")
    ordering_fields = ("sort_order", "created_at")

    def get_queryset(self):
        queryset = Banner.objects.all()
        if self.request.user and self.request.user.is_staff:
            return queryset
        return queryset.filter(is_active=True)


class SiteSettingView(generics.GenericAPIView):
    serializer_class = SiteSettingSerializer

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAdminUser()]
        return []

    def get(self, request):
        cached = cache.get("core:site-settings")
        if cached:
            return Response(cached)

        data = SiteSettingSerializer(SiteSetting.get_solo()).data
        cache.set("core:site-settings", data, timeout=300)
        return Response(data)

    def patch(self, request):
        settings_obj = SiteSetting.get_solo()
        serializer = self.get_serializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        cache.delete("core:site-settings")
        return Response(serializer.data)


class ContactMessageCreateView(generics.CreateAPIView):
    queryset = ContactMessage.objects.all()
    serializer_class = ContactMessageSerializer
    permission_classes = [AllowAny]
    throttle_scope = "contact"


class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all()
    serializer_class = PromotionSerializer
    permission_classes = [IsAdminUser]
    search_fields = ("code", "title", "description")
    ordering_fields = ("created_at", "starts_at", "ends_at", "times_redeemed")
