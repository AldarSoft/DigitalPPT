from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class HasStaffPermission(BasePermission):
    permission_codename = ""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
            and (
                user.is_superuser
                or user.has_perm(f"users.{self.permission_codename}")
            )
        )


class CanManageUsers(HasStaffPermission):
    permission_codename = "manage_users"


class CanConfirmBankPayments(HasStaffPermission):
    permission_codename = "confirm_bank_payments"


class CanManagePaymentSettings(HasStaffPermission):
    permission_codename = "manage_payment_settings"


class CanRunPaymentSimulations(HasStaffPermission):
    permission_codename = "run_payment_simulations"


class CanManageInventory(HasStaffPermission):
    permission_codename = "manage_inventory"


class CanManageQuotes(HasStaffPermission):
    permission_codename = "manage_quotes"


class CanManageOrders(HasStaffPermission):
    permission_codename = "manage_orders"


class CanManageSiteSettings(HasStaffPermission):
    permission_codename = "manage_site_settings"


class CanManageLicenses(HasStaffPermission):
    permission_codename = "manage_licenses"


class StaffPermissionOrReadOnly(BasePermission):
    permission_codename = ""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return HasStaffPermission.has_permission(self, request, view)


class CanManageInventoryOrReadOnly(StaffPermissionOrReadOnly):
    permission_codename = "manage_inventory"


class CanManageSiteSettingsOrReadOnly(StaffPermissionOrReadOnly):
    permission_codename = "manage_site_settings"
