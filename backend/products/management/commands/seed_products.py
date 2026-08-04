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
            "inventory_quantity": int(entry.get("stock", 0) or 0),
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

    @staticmethod
    def _portable_media_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme and parsed.path.startswith("/media/"):
            return parsed.path
        return value
