from django.db import migrations, models


def rebrand_legacy_site_settings(apps, schema_editor):
    SiteSetting = apps.get_model("core", "SiteSetting")
    SiteSetting.objects.filter(site_name="Rack & Bracket").update(
        site_name="Digital PTT",
        tagline="Professional push-to-talk radios and field-ready communication gear",
        support_email="",
        support_phone="",
        company_address="",
        facebook_url="",
        twitter_url="",
        linkedin_url="",
        instagram_url="",
        working_hours="",
        about_story=(
            "Digital PTT supplies professional push-to-talk over cellular radios, "
            "dual-mode devices, and field-ready accessories for connected teams."
        ),
        about_mission=(
            "To help field teams communicate clearly and reliably across vehicles, "
            "sites, and nationwide networks."
        ),
        about_vision=(
            "To make dependable, connected radio communication accessible to every "
            "operational team."
        ),
        about_image_url="",
        about_team=[],
        about_stats=[],
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0006_promotion")]

    operations = [
        migrations.AlterField(
            model_name="sitesetting",
            name="site_name",
            field=models.CharField(default="Digital PTT", max_length=255),
        ),
        migrations.RunPython(rebrand_legacy_site_settings, migrations.RunPython.noop),
    ]
