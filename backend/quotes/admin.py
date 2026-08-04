from django.contrib import admin

from quotes.models import QuoteRequest, QuoteRequestItem


class QuoteRequestItemInline(admin.TabularInline):
    model = QuoteRequestItem
    extra = 0
    readonly_fields = ("product_name", "sku", "quantity", "specifications")


@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    inlines = [QuoteRequestItemInline]
    list_display = (
        "quote_number",
        "requester_contact_person",
        "requester_email",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "quote_number",
        "requester_contact_person",
        "requester_email",
        "requester_company_name",
    )
    readonly_fields = ("quote_number", "created_at", "updated_at")


@admin.register(QuoteRequestItem)
class QuoteRequestItemAdmin(admin.ModelAdmin):
    list_display = ("quote_request", "product_name", "quantity")
    search_fields = ("quote_request__quote_number", "product_name", "sku")
