from django.contrib import admin

from payments.models import PaymentAttempt, PaymentProvider


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ("display_name", "code", "is_enabled", "test_mode", "sort_order")
    list_editable = ("is_enabled", "sort_order")
    search_fields = ("display_name", "code")


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ("reference", "order", "provider", "amount", "currency", "status", "is_test", "created_at")
    list_filter = ("status", "provider", "is_test")
    search_fields = ("reference", "order__order_number", "external_reference")
    readonly_fields = ("reference", "idempotency_key", "amount", "currency", "is_test", "external_reference", "created_by", "created_at", "updated_at")
