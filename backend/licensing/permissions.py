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
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or cls.membership_for(user=user, organization=organization))
        )

    @classmethod
    def can_manage_licenses(cls, *, user, organization):
        return cls.can_view(user=user, organization=organization)

    @classmethod
    def can_manage_team(cls, *, user, organization):
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        membership = cls.membership_for(user=user, organization=organization)
        return bool(membership and membership.role == OrganizationMembership.Role.OWNER)
