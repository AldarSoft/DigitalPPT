from django.contrib import admin

from core.models import Banner, ContactMessage, NotificationJob, OperationalRun, SiteSetting, UserNotification


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


@admin.register(OperationalRun)
class OperationalRunAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "started_at", "finished_at")
    list_filter = ("kind", "status")
    readonly_fields = ("kind", "status", "started_at", "finished_at", "details", "error", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("title", "message", "recipient__email")
    readonly_fields = ("recipient", "title", "message", "url", "created_at", "updated_at")
