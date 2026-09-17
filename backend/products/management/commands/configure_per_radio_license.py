from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from licensing.models import License
from orders.models import Order, OrderItem
from products.models import Product


class Command(BaseCommand):
    help = (
        "Convert one license product to per-radio annual billing after checking "
        "for incompatible open orders."
    )

    def add_arguments(self, parser):
        parser.add_argument("--sku", required=True, help="License product SKU.")
        parser.add_argument(
            "--unit-price",
            default="120.00",
            help="Annual price for one radio (default: 120.00).",
        )
        parser.add_argument(
            "--term-days",
            type=int,
            default=365,
            help="License term in days (default: 365).",
        )

    def handle(self, *args, **options):
        try:
            unit_price = Decimal(options["unit_price"])
        except InvalidOperation as exc:
            raise CommandError("--unit-price must be a valid decimal amount.") from exc

        if unit_price <= 0:
            raise CommandError("--unit-price must be greater than zero.")
        if options["term_days"] <= 0:
            raise CommandError("--term-days must be greater than zero.")

        with transaction.atomic():
            try:
                product = Product.objects.select_for_update().get(sku=options["sku"])
            except Product.DoesNotExist as exc:
                raise CommandError(
                    f"No product exists with SKU '{options['sku']}'."
                ) from exc

            if product.licensing_role != Product.LicensingRole.LICENSE_PRODUCT:
                raise CommandError(
                    f"Product '{product.sku}' is not a license product."
                )

            current_billing_model = (
                product.license_billing_model
                or Product.LicenseBillingModel.LEGACY_CAPACITY
            )
            if current_billing_model != Product.LicenseBillingModel.PER_RADIO:
                issued_licenses = list(
                    License.objects.filter(license_product=product)
                    .order_by("pk")
                    .values_list("license_number", flat=True)[:6]
                )
                if issued_licenses:
                    shown = ", ".join(issued_licenses[:5])
                    if len(issued_licenses) > 5:
                        shown += ", ..."
                    raise CommandError(
                        "Cannot convert a plan that has issued legacy licenses: "
                        f"{shown}. Create a separate per-radio license product and "
                        "assign it to the radio products instead."
                    )

                open_orders = (
                    OrderItem.objects.filter(
                        product=product,
                        order__status__in=[Order.Status.DRAFT, Order.Status.PENDING],
                    )
                    .order_by()
                    .values_list("order__order_number", flat=True)
                    .distinct()
                )
                order_numbers = list(open_orders[:6])
                if order_numbers:
                    shown = ", ".join(order_numbers[:5])
                    if len(order_numbers) > 5:
                        shown += ", ..."
                    raise CommandError(
                        "Cannot change this plan while draft or pending legacy "
                        f"orders reference it: {shown}. Cancel or complete those "
                        "orders, then run the command again."
                    )

            product.license_billing_model = Product.LicenseBillingModel.PER_RADIO
            product.license_capacity = None
            product.license_term_days = options["term_days"]
            product.price = unit_price
            product.sale_price = None
            product.bulk_minimum_quantity = None
            product.bulk_unit_price = None
            product.full_clean()
            product.save(
                update_fields=[
                    "license_billing_model",
                    "license_capacity",
                    "license_term_days",
                    "price",
                    "sale_price",
                    "bulk_minimum_quantity",
                    "bulk_unit_price",
                    "updated_at",
                ]
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Configured {product.sku} for {unit_price:.2f} per radio "
                f"for {product.license_term_days} days."
            )
        )
