from django.contrib import admin

from licensing.models import (
    License,
    LicenseEvent,
    LicenseOrderItemProvisioning,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    ProductLicenseAllocation,
)


class OrganizationMembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0
    autocomplete_fields = ("user", "invited_by")


class OrganizationInvitationInline(admin.TabularInline):
    model = OrganizationInvitation
    extra = 0
    fields = ("email", "role", "status_display", "expires_at", "invited_by")
    readonly_fields = ("status_display",)
    autocomplete_fields = ("invited_by",)
    show_change_link = True

    @admin.display(description="Status")
    def status_display(self, obj):
        return obj.status if obj else "pending"


class LicenseInline(admin.TabularInline):
    model = License
    extra = 0
    fields = (
        "license_number",
        "name",
        "status",
        "capacity",
        "used_capacity",
        "expires_on",
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "public_id", "billing_email", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "billing_email", "public_id")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("created_by",)
    inlines = (LicenseInline, OrganizationMembershipInline, OrganizationInvitationInline)


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("organization__name", "user__email", "user__username")
    autocomplete_fields = ("organization", "user", "invited_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "role", "status_display", "expires_at")
    list_filter = ("role", "accepted_at", "revoked_at")
    search_fields = ("email", "organization__name")
    autocomplete_fields = ("organization", "invited_by", "accepted_by")
    readonly_fields = (
        "token_hash",
        "status_display",
        "accepted_at",
        "revoked_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Status")
    def status_display(self, obj):
        return obj.status


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = (
        "license_number",
        "organization",
        "name",
        "status",
        "capacity",
        "used_capacity",
        "available_capacity_display",
        "expires_on",
    )
    list_filter = ("status", "license_product")
    search_fields = (
        "license_number",
        "name",
        "organization__name",
        "organization__billing_email",
    )
    readonly_fields = (
        "organization",
        "license_product",
        "license_number",
        "name",
        "status",
        "capacity",
        "used_capacity",
        "available_capacity_display",
        "starts_on",
        "expires_on",
        "renews_on",
        "source_order_item",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Available")
    def available_capacity_display(self, obj):
        return obj.available_capacity

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductLicenseAllocation)
class ProductLicenseAllocationAdmin(admin.ModelAdmin):
    list_display = ("license", "product", "order_item", "quantity", "status", "created_at")
    list_filter = ("status", "product")
    search_fields = (
        "license__license_number",
        "license__organization__name",
        "product__name",
        "product__sku",
        "order_item__order__order_number",
    )
    readonly_fields = (
        "license",
        "product",
        "order_item",
        "quantity",
        "status",
        "released_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LicenseOrderItemProvisioning)
class LicenseOrderItemProvisioningAdmin(admin.ModelAdmin):
    list_display = (
        "order_item",
        "organization",
        "operation",
        "completed_at",
    )
    list_filter = ("operation", "completed_at")
    search_fields = (
        "order_item__order__order_number",
        "order_item__product_name",
        "organization__name",
    )
    readonly_fields = (
        "organization",
        "order_item",
        "operation",
        "created_license_ids",
        "renewed_license_ids",
        "allocation_ids",
        "completed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LicenseEvent)
class LicenseEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "organization", "license", "event_type", "actor")
    list_filter = ("event_type", "occurred_at")
    search_fields = (
        "organization__name",
        "license__license_number",
        "actor__email",
    )
    readonly_fields = (
        "organization",
        "license",
        "invitation",
        "event_type",
        "actor",
        "metadata",
        "occurred_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "occurred_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
