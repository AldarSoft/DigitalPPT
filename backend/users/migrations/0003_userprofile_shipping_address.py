from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_portable_avatar_paths"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="shipping_address_line_1",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="shipping_address_line_2",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="shipping_city",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="shipping_country",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="shipping_postal_code",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="shipping_state",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="use_different_shipping_address",
            field=models.BooleanField(default=False),
        ),
    ]
