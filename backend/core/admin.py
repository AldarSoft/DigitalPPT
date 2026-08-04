from django.contrib import admin

from core.models import Banner, ContactMessage, NotificationJob, SiteSetting


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "sort_order", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "subtitle", "description")


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ("site_name", "support_email", "default_currency", "updated_at")

    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "is_read", "created_at")
    list_filter = ("is_read", "subject")
    search_fields = ("name", "email", "phone", "message")
    readonly_fields = ("name", "email", "phone", "subject", "message", "created_at")


@admin.register(NotificationJob)
class NotificationJobAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "attempts", "available_at", "processed_at")
    list_filter = ("kind", "status")
    readonly_fields = (
        "kind",
        "payload",
        "status",
        "attempts",
        "available_at",
        "processed_at",
        "last_error",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False
