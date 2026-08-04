from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import Category, Product, ProductImage, ProductSpecification


CATALOG = [
    {
        "category": "POC Radios",
        "name": "IPTT510 - POC handheld radio",
        "slug": "iptt510",
        "sku": "IPTT510",
        "price": "120.00",
        "stock": 18,
        "image": "/images/radio-510.png",
        "short": "Compact 4G LTE push-to-talk radio for dependable team communication.",
        "specs": {"Network": "4G LTE", "Battery": "3000 mAh", "SIM": "Dual SIM"},
        "featured": True,
    },
    {
        "category": "POC Radios",
        "name": "IPTT810 / IPTT820",
        "slug": "iptt810-iptt820",
        "sku": "IPTT810",
        "price": "430.00",
        "stock": 12,
        "image": "/images/radio-810.png",
        "short": "Android handheld POC radio for advanced field workflows.",
        "specs": {"Network": "4G LTE / Wi-Fi", "Operating system": "Android"},
        "featured": True,
    },
    {
        "category": "POC Radios",
        "name": "IPTT81 Dual Mode",
        "slug": "iptt81-dual-mode",
        "sku": "IPTT81",
        "price": "340.00",
        "stock": 4,
        "image": "/images/radio-t81.png",
        "short": "POC and analog dual-mode communications in one handheld.",
        "specs": {"Network": "POC + Analog", "Protection": "IP68"},
        "featured": True,
    },
    {
        "category": "POC Radios",
        "name": "IPTT710 Android",
        "slug": "iptt710-android",
        "sku": "IPTT710",
        "price": "430.00",
        "stock": 9,
        "image": "/images/radio-710.png",
        "short": "Connected Android POC handheld for data and instant voice.",
        "specs": {"Network": "4G LTE", "Operating system": "Android"},
        "featured": True,
    },
    {
        "category": "POC Radios",
        "name": "IPTT760 ATEX",
        "slug": "iptt760-atex",
        "sku": "IPTT760",
        "price": "680.00",
        "stock": 2,
        "image": "/images/radio-760.png",
        "short": "ATEX-rated POC radio for hazardous industrial environments.",
        "specs": {"Rating": "ATEX", "Protection": "IP68"},
        "featured": False,
    },
    {
        "category": "Radio Holsters",
        "name": "Field Harness Carry System",
        "slug": "field-harness-carry-system",
        "sku": "HOLS001",
        "price": "18.00",
        "stock": 24,
        "image": "/images/holsters-hero.png",
        "short": "Balanced hands-free chest carry for professional radios.",
        "specs": {"Carry style": "Chest harness", "Material": "Reinforced nylon"},
        "featured": False,
    },
    {
        "category": "Radio Holsters",
        "name": "Lightweight Chest Pack",
        "slug": "lightweight-chest-pack",
        "sku": "HOLS002",
        "price": "15.00",
        "stock": 26,
        "image": "/images/holsters-hero.png",
        "short": "Compact radio chest pack with adjustable field straps.",
        "specs": {"Carry style": "Chest pack", "Fit": "Universal"},
        "featured": False,
    },
    {
        "category": "Radio Holsters",
        "name": "Universal Shoulder Holster",
        "slug": "universal-shoulder-holster",
        "sku": "HOLS003",
        "price": "12.00",
        "stock": 20,
        "image": "/images/holsters-hero.png",
        "short": "Fast-access shoulder holster for compact handheld radios.",
        "specs": {"Carry style": "Shoulder", "Fit": "Universal"},
        "featured": False,
    },
]


class Command(BaseCommand):
    help = "Create or refresh the Digital PTT development catalog."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        updated = 0

        for entry in CATALOG:
            category, _ = Category.objects.get_or_create(
                name=entry["category"],
                defaults={
                    "description": (
                        "Nationwide push-to-talk radios for connected teams."
                        if entry["category"] == "POC Radios"
                        else "Field-ready carry systems for professional radios."
                    ),
                    "is_active": True,
                },
            )
            product, was_created = Product.objects.update_or_create(
                sku=entry["sku"],
                defaults={
                    "category": category,
                    "name": entry["name"],
                    "slug": entry["slug"],
                    "brand": "Digital PTT",
                    "short_description": entry["short"],
                    "description": entry["short"],
                    "price": Decimal(entry["price"]),
                    "inventory_quantity": entry["stock"],
                    "status": Product.Status.PUBLISHED,
                    "is_featured": entry["featured"],
                    "is_active": True,
                },
            )
            ProductImage.objects.update_or_create(
                product=product,
                is_primary=True,
                defaults={
                    "image_url": entry["image"],
                    "alt_text": entry["name"],
                    "sort_order": 0,
                },
            )
            product.specifications.all().delete()
            ProductSpecification.objects.bulk_create(
                [
                    ProductSpecification(
                        product=product,
                        key=key,
                        value=value,
                        sort_order=index,
                    )
                    for index, (key, value) in enumerate(entry["specs"].items())
                ]
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Digital PTT catalog ready. Created: {created}, updated: {updated}."
            )
        )
