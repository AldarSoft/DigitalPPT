from django.db import migrations


LEGACY_CATEGORY_SLUGS = (
    "cable-management",
    "cooling-solutions",
    "mounting-accessories",
    "power-distribution",
    "server-racks",
    "wall-mount-brackets",
)


def remove_legacy_rack_catalog(apps, schema_editor):
    Category = apps.get_model("products", "Category")
    Product = apps.get_model("products", "Product")

    Product.objects.filter(category__slug__in=LEGACY_CATEGORY_SLUGS).delete()
    Category.objects.filter(slug__in=LEGACY_CATEGORY_SLUGS).delete()


class Migration(migrations.Migration):
    dependencies = [("products", "0004_portable_media_paths")]

    operations = [
        migrations.RunPython(remove_legacy_rack_catalog, migrations.RunPython.noop),
    ]
