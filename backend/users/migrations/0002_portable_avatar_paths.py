from urllib.parse import urlparse

from django.db import migrations, models


def normalize_avatar_paths(apps, schema_editor):
    UserProfile = apps.get_model("users", "UserProfile")
    for profile in UserProfile.objects.exclude(avatar_url="").iterator():
        parsed = urlparse(profile.avatar_url)
        if parsed.scheme and parsed.path.startswith("/media/"):
            profile.avatar_url = parsed.path
            profile.save(update_fields=["avatar_url"])


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="avatar_url",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.RunPython(normalize_avatar_paths, migrations.RunPython.noop),
    ]
