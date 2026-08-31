from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils import timezone

from users.models import User, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0
    can_delete = False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [UserProfileInline]
    list_display = (
        "email",
        "username",
        "first_name",
        "last_name",
        "phone_number",
        "is_customer",
        "is_staff",
        "is_active",
        "email_verified_at",
    )
    list_filter = ("is_customer", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "username", "first_name", "last_name", "phone_number")
    ordering = ("email",)
    readonly_fields = ("last_login", "date_joined", "email_verified_at", "created_at", "updated_at")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Commerce",
            {
                "fields": (
                    "phone_number",
                    "is_customer",
                    "email_verified_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not change and obj.is_staff and obj.email_verified_at is None:
            obj.email_verified_at = timezone.now()
        super().save_model(request, obj, form, change)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Commerce",
            {
                "fields": ("email", "phone_number", "is_customer"),
            },
        ),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company_name", "job_title", "country", "city")
    list_filter = ("country", "city")
    search_fields = ("user__email", "company_name", "job_title", "city", "country")
