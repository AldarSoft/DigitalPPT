from urllib.parse import urlparse

from django.db import migrations, models


def normalize_media_paths(apps, schema_editor):
    Category = apps.get_model("products", "Category")
    ProductImage = apps.get_model("products", "ProductImage")

    for model in (Category, ProductImage):
        for instance in model.objects.exclude(image_url="").iterator():
            parsed = urlparse(instance.image_url)
            if parsed.scheme and parsed.path.startswith("/media/"):
                instance.image_url = parsed.path
                instance.save(update_fields=["image_url"])


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0003_category_image_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="category",
            name="image_url",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="productimage",
            name="image_url",
            field=models.CharField(max_length=500),
        ),
        migrations.RunPython(normalize_media_paths, migrations.RunPython.noop),
    ]
