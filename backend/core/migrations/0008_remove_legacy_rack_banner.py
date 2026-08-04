from django.db import migrations


LEGACY_BANNER_TITLES = (
    "Premium Server Racks & Mounting Solutions",
)


def remove_legacy_rack_banner(apps, schema_editor):
    Banner = apps.get_model("core", "Banner")
    Banner.objects.filter(title__in=LEGACY_BANNER_TITLES).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0007_rebrand_digital_ptt")]

    operations = [
        migrations.RunPython(remove_legacy_rack_banner, migrations.RunPython.noop),
    ]
