from __future__ import annotations

from django.contrib.auth.models import Group, Permission


class StaffRole:
    SUPPORT = "Support"
    INVENTORY_OPERATOR = "Inventory Operator"
    QUOTE_ADMINISTRATOR = "Quote Administrator"
    FINANCE = "Finance / Payment Confirmer"
    USER_ADMINISTRATOR = "User Administrator"
    SUPER_ADMINISTRATOR = "Super Administrator"


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

STAFF_ROLE_PERMISSIONS = {
    StaffRole.SUPPORT: ("access_staff_workspace",),
    StaffRole.INVENTORY_OPERATOR: (
        "access_staff_workspace",
        "manage_inventory",
        "manage_orders",
    ),
    StaffRole.QUOTE_ADMINISTRATOR: (
        "access_staff_workspace",
        "manage_quotes",
        "manage_orders",
    ),
    StaffRole.FINANCE: (
        "access_staff_workspace",
        "confirm_bank_payments",
        "manage_payment_settings",
    ),
    StaffRole.USER_ADMINISTRATOR: (
        "access_staff_workspace",
        "manage_users",
    ),
    StaffRole.SUPER_ADMINISTRATOR: tuple(STAFF_PERMISSIONS),
}

STAFF_ROLE_CHOICES = tuple((name, name) for name in STAFF_ROLE_PERMISSIONS)


def role_names_for_user(user) -> list[str]:
    if not user or not user.is_staff:
        return []
    if user.is_superuser:
        return [StaffRole.SUPER_ADMINISTRATOR]
    return list(
        user.groups.filter(name__in=STAFF_ROLE_PERMISSIONS)
        .order_by("name")
        .values_list("name", flat=True)
    )


def assign_staff_roles(user, role_names) -> None:
    selected = set(role_names or [])
    role_groups = Group.objects.filter(name__in=STAFF_ROLE_PERMISSIONS)
    user.groups.remove(*role_groups)
    if not user.is_staff:
        return
    groups = list(Group.objects.filter(name__in=selected))
    if len(groups) != len(selected):
        raise ValueError("One or more staff roles are not configured.")
    user.groups.add(*groups)


def configure_staff_roles() -> None:
    permissions = {
        permission.codename: permission
        for permission in Permission.objects.filter(
            content_type__app_label="users",
            codename__in=STAFF_PERMISSIONS,
        )
    }
    for role_name, codenames in STAFF_ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role_name)
        group.permissions.set(
            [permissions[codename] for codename in codenames if codename in permissions]
        )
