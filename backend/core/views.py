from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from common.permissions import CanManageSiteSettings, CanManageSiteSettingsOrReadOnly
from core.models import Banner, ContactMessage, Promotion, SiteSetting, UserNotification
from core.serializers import (
    AdminSiteSettingSerializer,
    PublicSiteSettingSerializer,
    UserNotificationSerializer,
    BannerSerializer,
    ContactMessageSerializer,
    PromotionSerializer,
)


class UserNotificationListView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserNotificationSerializer

    def get(self, request):
        queryset = UserNotification.objects.filter(recipient=request.user)
        return Response({
            "unread_count": queryset.filter(is_read=False).count(),
            "notifications": self.get_serializer(queryset[:20], many=True).data,
        })


class UserNotificationReadView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserNotificationSerializer

    def patch(self, request, pk):
        notification = get_object_or_404(
            UserNotification,
            pk=pk,
            recipient=request.user,
        )
        notification.is_read = True
        notification.save(update_fields=["is_read", "updated_at"])
        return Response(self.get_serializer(notification).data)


class BannerViewSet(viewsets.ModelViewSet):
    serializer_class = BannerSerializer
    permission_classes = [CanManageSiteSettingsOrReadOnly]
    search_fields = ("title", "subtitle")
    ordering_fields = ("sort_order", "created_at")

    def get_queryset(self):
        queryset = Banner.objects.all()
        if self.request.user and (
            self.request.user.is_superuser
            or self.request.user.has_perm("users.manage_site_settings")
        ):
            return queryset
        return queryset.filter(is_active=True)


class SiteSettingView(generics.GenericAPIView):
    serializer_class = PublicSiteSettingSerializer
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(self.get_serializer(SiteSetting.get_solo()).data)


class AdminSiteSettingView(generics.GenericAPIView):
    serializer_class = AdminSiteSettingSerializer
    permission_classes = [CanManageSiteSettings]

    def get(self, request):
        return Response(self.get_serializer(SiteSetting.get_solo()).data)

    def patch(self, request):
        settings_obj = SiteSetting.get_solo()
        serializer = self.get_serializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ContactMessageCreateView(generics.CreateAPIView):
    queryset = ContactMessage.objects.all()
    serializer_class = ContactMessageSerializer
    permission_classes = [AllowAny]
    throttle_scope = "contact"


class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all()
    serializer_class = PromotionSerializer
    permission_classes = [CanManageSiteSettings]
    search_fields = ("code", "title", "description")
    ordering_fields = ("created_at", "starts_at", "ends_at", "times_redeemed")
