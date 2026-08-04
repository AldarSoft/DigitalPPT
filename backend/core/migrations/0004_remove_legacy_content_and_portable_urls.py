from urllib.parse import urlparse

from django.db import migrations, models


def normalize_internal_urls(apps, schema_editor):
    Banner = apps.get_model("core", "Banner")
    SiteSetting = apps.get_model("core", "SiteSetting")

    for banner in Banner.objects.all().iterator():
        changed = []
        image = urlparse(banner.image_url)
        if image.scheme and image.path.startswith("/media/"):
            banner.image_url = image.path
            changed.append("image_url")

        cta = urlparse(banner.cta_url)
        if cta.hostname in {"localhost", "127.0.0.1"} and cta.path:
            banner.cta_url = cta.path
            changed.append("cta_url")

        if changed:
            banner.save(update_fields=changed)

    for settings in SiteSetting.objects.exclude(about_image_url="").iterator():
        parsed = urlparse(settings.about_image_url)
        if parsed.scheme and parsed.path.startswith("/media/"):
            settings.about_image_url = parsed.path
            settings.save(update_fields=["about_image_url"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_sitesetting_facebook_url_sitesetting_instagram_url_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="Testimonial"),
        migrations.RemoveField(model_name="sitesetting", name="from_email"),
        migrations.RemoveField(model_name="sitesetting", name="smtp_host"),
        migrations.RemoveField(model_name="sitesetting", name="smtp_password"),
        migrations.RemoveField(model_name="sitesetting", name="smtp_port"),
        migrations.RemoveField(model_name="sitesetting", name="smtp_username"),
        migrations.AlterField(
            model_name="banner",
            name="cta_url",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="banner",
            name="image_url",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="sitesetting",
            name="about_image_url",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.RunPython(normalize_internal_urls, migrations.RunPython.noop),
    ]
