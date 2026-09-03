from django.db import migrations, models
from django.db.models.functions import Lower


STAFF_PERMISSIONS = {
    "access_staff_workspace": "Can access the staff workspace",
    "manage_inventory": "Can manage products and inventory",
    "manage_quotes": "Can review quotes and issue invoices",
    "manage_orders": "Can manage orders and fulfillment",
    "confirm_bank_payments": "Can confirm reconciled bank payments",
    "manage_payment_settings": "Can manage payment availability",
    "manage_users": "Can manage customer accounts",
    "manage_site_settings": "Can manage site settings",
    "manage_licenses": "Can manage organization licenses",
    "run_payment_simulations": "Can run development payment simulations",
}

ROLE_PERMISSIONS = {
    "Support": ("access_staff_workspace",),
    "Inventory Operator": ("access_staff_workspace", "manage_inventory", "manage_orders"),
    "Quote Administrator": ("access_staff_workspace", "manage_quotes", "manage_orders"),
    "Finance / Payment Confirmer": (
        "access_staff_workspace",
        "confirm_bank_payments",
        "manage_payment_settings",
    ),
    "User Administrator": ("access_staff_workspace", "manage_users"),
    "Super Administrator": tuple(STAFF_PERMISSIONS),
}


def normalize_emails(apps, schema_editor):
    User = apps.get_model("users", "User")
    seen = {}
    for user in User.objects.order_by("pk").iterator():
        normalized = user.email.strip().casefold()
        if normalized in seen:
            raise RuntimeError(
                "Cannot add case-insensitive email uniqueness: "
                f"users {seen[normalized]} and {user.pk} share {normalized}."
            )
        seen[normalized] = user.pk
        if user.email != normalized:
            User.objects.filter(pk=user.pk).update(email=normalized)


def create_staff_roles(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("users", "User")

    content_type, _ = ContentType.objects.get_or_create(app_label="users", model="user")
    permissions = {}
    for codename, name in STAFF_PERMISSIONS.items():
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission

    groups = {}
    for role_name, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role_name)
        group.permissions.set([permissions[codename] for codename in codenames])
        groups[role_name] = group

    # Preserve current staff access explicitly. New staff accounts receive no
    # privileged role unless a super administrator assigns one.
    legacy_staff = User.objects.filter(is_staff=True, is_superuser=False)
    groups["Super Administrator"].user_set.add(*legacy_staff)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_user_email_verified_at"),
    ]

    operations = [
        migrations.RunPython(normalize_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("email"),
                name="users_user_email_ci_unique",
            ),
        ),
        migrations.AlterModelOptions(
            name="user",
            options={
                "permissions": list(STAFF_PERMISSIONS.items()),
                "verbose_name": "User",
                "verbose_name_plural": "Users",
            },
        ),
        migrations.RunPython(create_staff_roles, migrations.RunPython.noop),
    ]
