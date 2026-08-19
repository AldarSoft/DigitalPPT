from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.models import Category, Product, ProductImage, ProductSpecification


class Command(BaseCommand):
    help = "Import or update products from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=str(settings.BASE_DIR.parent / "products_mock.json"),
            help="Path to the products JSON file.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"]).expanduser().resolve()
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {file_path}: {exc}") from exc

        if not isinstance(payload, list):
            raise CommandError("Expected the JSON file to contain a list of products.")

        created_count = 0
        updated_count = 0

        payload.sort(
            key=lambda entry: entry.get("licensingRole")
            != Product.LicensingRole.LICENSE_PRODUCT
        )

        with transaction.atomic():
            for entry in payload:
                product, created = self._upsert_product(entry)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported products from {file_path}. Created: {created_count}, Updated: {updated_count}."
            )
        )

    def _upsert_product(self, entry: dict) -> tuple[Product, bool]:
        category = self._resolve_category(entry)
        images = entry.get("images", [])
        specifications = entry.get("specifications", [])
        licensing_role = entry.get("licensingRole", Product.LicensingRole.STANDARD)
        required_license_product = self._resolve_required_license_product(
            entry, licensing_role
        )
        license_capacity = self._to_optional_int(entry.get("licenseCapacity"))
        license_term_days = self._to_optional_int(entry.get("licenseTermDays"))
        self._validate_licensing_metadata(
            entry,
            licensing_role,
            required_license_product,
            license_capacity,
            license_term_days,
        )

        defaults = {
            "category": category,
            "name": entry["name"],
            "slug": entry.get("slug") or "",
            "brand": entry.get("brand", ""),
            "short_description": entry.get("shortDescription", ""),
            "description": entry.get("description", ""),
            "price": self._to_decimal(entry.get("price"), default="0"),
            "cost_price": self._to_optional_decimal(entry.get("costPrice")),
            "sale_price": self._to_optional_decimal(entry.get("salePrice")),
            "inventory_quantity": (
                0
                if licensing_role == Product.LicensingRole.LICENSE_PRODUCT
                else int(entry.get("stock", 0) or 0)
            ),
            "licensing_role": licensing_role,
            "required_license_product": required_license_product,
            "license_capacity": license_capacity,
            "license_term_days": license_term_days,
            "status": Product.Status.PUBLISHED,
            "is_featured": bool(entry.get("isFeatured", False)),
            "is_active": True,
        }

        product, created = Product.objects.update_or_create(
            sku=entry["sku"],
            defaults=defaults,
        )

        product.images.all().delete()
        product.specifications.all().delete()

        image_objects = []
        for index, image in enumerate(images):
            image_objects.append(
                ProductImage(
                    product=product,
                    image_url=self._portable_media_url(image["url"]),
                    alt_text=image.get("alt", ""),
                    is_primary=bool(image.get("isPrimary", False)),
                    sort_order=index,
                )
            )

        specification_objects = []
        for index, specification in enumerate(specifications):
            key = specification.get("key") or specification.get("name")
            value = specification.get("value")
            if not key or value in (None, ""):
                continue
            specification_objects.append(
                ProductSpecification(
                    product=product,
                    key=key,
                    value=str(value),
                    sort_order=index,
                )
            )

        if image_objects:
            ProductImage.objects.bulk_create(image_objects)
        if specification_objects:
            ProductSpecification.objects.bulk_create(specification_objects)

        return product, created

    def _validate_licensing_metadata(
        self,
        entry: dict,
        licensing_role: str,
        required_license_product: Product | None,
        license_capacity: int | None,
        license_term_days: int | None,
    ) -> None:
        valid_roles = {value for value, _label in Product.LicensingRole.choices}
        if licensing_role not in valid_roles:
            raise CommandError(
                f"Product '{entry.get('name')}' has invalid licensingRole "
                f"'{licensing_role}'."
            )
        if licensing_role == Product.LicensingRole.STANDARD:
            if required_license_product or license_capacity or license_term_days:
                raise CommandError(
                    f"Standard product '{entry.get('name')}' cannot set license metadata."
                )
        elif licensing_role == Product.LicensingRole.LICENSED_PRODUCT:
            if license_capacity or license_term_days:
                raise CommandError(
                    f"Licensed product '{entry.get('name')}' consumes capacity and "
                    "cannot supply capacity or a term."
                )
        elif not license_capacity or not license_term_days:
            raise CommandError(
                f"License product '{entry.get('name')}' requires positive "
                "licenseCapacity and licenseTermDays."
            )

    def _resolve_required_license_product(
        self, entry: dict, licensing_role: str
    ) -> Product | None:
        required_sku = entry.get("requiredLicenseSku")
        if licensing_role != Product.LicensingRole.LICENSED_PRODUCT:
            if required_sku:
                raise CommandError(
                    f"Product '{entry.get('name')}' cannot set requiredLicenseSku "
                    f"with licensingRole '{licensing_role}'."
                )
            return None
        if not required_sku:
            raise CommandError(
                f"Licensed product '{entry.get('name')}' requires requiredLicenseSku."
            )
        try:
            license_product = Product.objects.get(sku=required_sku)
        except Product.DoesNotExist as exc:
            raise CommandError(
                f"License product '{required_sku}' must appear before "
                f"'{entry.get('name')}' or already exist."
            ) from exc
        if license_product.licensing_role != Product.LicensingRole.LICENSE_PRODUCT:
            raise CommandError(f"Product '{required_sku}' is not a license product.")
        return license_product

    def _resolve_category(self, entry: dict) -> Category:
        category_id = entry.get("categoryId")
        if category_id:
            try:
                return Category.objects.get(pk=category_id)
            except Category.DoesNotExist:
                pass

        category_name = entry.get("categoryName")
        if category_name:
            try:
                return Category.objects.get(name=category_name)
            except Category.DoesNotExist as exc:
                raise CommandError(
                    f"Category not found for product '{entry.get('name')}'. "
                    f"Expected id '{category_id}' or name '{category_name}'."
                ) from exc

        raise CommandError(f"Missing category for product '{entry.get('name')}'.")

    def _to_decimal(self, value, default: str = "0") -> Decimal:
        if value in (None, ""):
            value = default
        return Decimal(str(value))

    def _to_optional_decimal(self, value) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))

    def _to_optional_int(self, value) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    @staticmethod
    def _portable_media_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme and parsed.path.startswith("/media/"):
            return parsed.path
        return value
