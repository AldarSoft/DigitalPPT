from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0002_product_cost_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="image_url",
            field=models.URLField(blank=True),
        ),
    ]
