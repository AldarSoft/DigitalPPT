import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_alter_notificationjob_kind"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdminNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField(blank=True)),
                ("url", models.CharField(max_length=500)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="admin_notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(
            model_name="adminnotification",
            index=models.Index(fields=["recipient", "is_read", "created_at"], name="core_adminn_recipient_idx"),
        ),
    ]
