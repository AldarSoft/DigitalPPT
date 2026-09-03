from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_sitesetting_bank_account_number_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="RequestThrottleBucket",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.CharField(max_length=64, unique=True)),
                ("scope", models.CharField(db_index=True, max_length=64)),
                ("request_count", models.PositiveIntegerField(default=0)),
                ("window_started_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField(db_index=True)),
            ],
            options={
                "ordering": ("expires_at", "id"),
                "indexes": [
                    models.Index(
                        fields=["scope", "expires_at"],
                        name="core_throttle_scope_exp_idx",
                    ),
                ],
            },
        ),
    ]
