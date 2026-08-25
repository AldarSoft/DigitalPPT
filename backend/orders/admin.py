from django.contrib import admin
from django.db.models import Sum

from orders.models import Order, OrderItem
from orders.services import OrderService


def recalculate_order_totals(order):
    for item in order.items.all():
        line_total = item.unit_price * item.quantity
        if item.line_total != line_total:
            item.line_total = line_total
            item.save(update_fields=["line_total", "updated_at"])

    subtotal = order.items.aggregate(total=Sum("line_total"))["total"] or 0
    order.subtotal = subtotal
    order.tax_amount = 0
    order.shipping_fee = 0
    order.total = subtotal
    order.save(update_fields=["subtotal", "tax_amount", "shipping_fee", "total", "updated_at"])


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product", "product_name", "sku", "unit_price", "quantity", "line_total")

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.stock_deducted:
            return self.fields
        return ()

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.stock_deducted)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    exclude = ("tax_amount", "shipping_fee")
    list_display = (
        "order_number",
        "quote_request",
        "organization",
        "customer_email",
        "status",
        "subtotal",
        "total",
        "created_at",
    )
    list_filter = ("status", "organization", "created_at", "shipping_country")
    search_fields = (
        "order_number",
        "customer_email",
        "customer_first_name",
        "customer_last_name",
        "organization__name",
    )
    readonly_fields = (
        "order_number",
        "subtotal",
        "total",
        "stock_deducted",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data:
            target_status = obj.status
            previous = Order.objects.get(pk=obj.pk)
            obj.status = previous.status
            super().save_model(request, obj, form, change)
            updated = OrderService.update_status(order=obj, new_status=target_status)
            obj.status = updated.status
            obj.stock_deducted = updated.stock_deducted
            return
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        recalculate_order_totals(form.instance)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "quantity", "unit_price", "line_total")
    search_fields = ("order__order_number", "product_name", "sku")

    def save_model(self, request, obj, form, change):
        obj.line_total = obj.unit_price * obj.quantity
        super().save_model(request, obj, form, change)
        recalculate_order_totals(obj.order)

    def delete_model(self, request, obj):
        order = obj.order
        super().delete_model(request, obj)
        recalculate_order_totals(order)
