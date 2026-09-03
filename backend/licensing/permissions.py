from __future__ import annotations

from licensing.models import OrganizationMembership


class OrganizationAccessPolicy:
    @staticmethod
    def membership_for(*, user, organization):
        if not user or not user.is_authenticated:
            return None
        return OrganizationMembership.objects.filter(
            organization=organization,
            user=user,
            is_active=True,
        ).first()

    @classmethod
    def can_view(cls, *, user, organization):
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return user.is_superuser or user.has_perm("users.manage_licenses")
        return bool(cls.membership_for(user=user, organization=organization))

    @classmethod
    def can_manage_licenses(cls, *, user, organization):
        return cls.can_view(user=user, organization=organization)

    @classmethod
    def can_manage_billing(cls, *, user, organization):
        """Members may pay license renewals for their organization."""
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return user.is_superuser or user.has_perm("users.confirm_bank_payments")
        return bool(cls.membership_for(user=user, organization=organization))

    @classmethod
    def can_pay_orders(cls, *, user, organization):
        """Organization orders are paid by the Owner (or authorized staff) only."""
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return user.is_superuser or user.has_perm("users.confirm_bank_payments")
        membership = cls.membership_for(user=user, organization=organization)
        return bool(membership and membership.role == OrganizationMembership.Role.OWNER)

    @classmethod
    def can_view_orders(cls, *, user, organization):
        """Organization orders (addresses and billing) are visible to the Owner and staff only."""
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return user.is_superuser or user.has_perm("users.manage_orders")
        membership = cls.membership_for(user=user, organization=organization)
        return bool(membership and membership.role == OrganizationMembership.Role.OWNER)

    @classmethod
    def can_manage_team(cls, *, user, organization):
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return user.is_superuser or user.has_perm("users.manage_licenses")
        membership = cls.membership_for(user=user, organization=organization)
        return bool(membership and membership.role == OrganizationMembership.Role.OWNER)
