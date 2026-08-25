from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("licensing", "0004_alter_licenseevent_event_type")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="status",
            field=models.CharField(
                choices=[("draft", "Draft"), ("active", "Active"), ("inactive", "Inactive")],
                db_index=True,
                default="active",
                max_length=16,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="organizationinvitation",
            name="licensing_invitations_are_for_license_managers",
        ),
        migrations.AddIndex(
            model_name="organization",
            index=models.Index(fields=["status", "is_active"], name="licensing_o_status_be764b_idx"),
        ),
    ]
