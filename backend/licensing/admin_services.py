from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Prefetch
from django.utils import timezone

from core.models import UserNotification
from licensing.models import (
    License,
    LicenseEvent,
    Organization,
    OrganizationMembership,
    ProductLicenseAllocation,
)
from licensing.services import ClientLicenseDetailService, LicenseLifecycleService
from payments.models import PaymentAttempt


class AdminOrganizationLicenseService:
    ACTIVE_STATUSES = (License.Status.ACTIVE, License.Status.EXPIRING_SOON)

    @staticmethod
    def _display_name(user):
        return user.get_full_name().strip() or user.email or user.get_username()

    @classmethod
    def queryset(cls, *, search="", status="", product=""):
        queryset = Organization.objects.filter(licenses__isnull=False)
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search)
                | models.Q(billing_email__icontains=search)
                | models.Q(memberships__user__email__icontains=search)
                | models.Q(memberships__user__first_name__icontains=search)
                | models.Q(memberships__user__last_name__icontains=search)
                | models.Q(licenses__license_number__icontains=search)
                | models.Q(licenses__license_product__name__icontains=search)
                | models.Q(licenses__license_product__sku__icontains=search)
            )
        if status:
            queryset = queryset.filter(licenses__status=status)
        if product:
            product_filter = (
                models.Q(licenses__license_product__sku__iexact=product)
                | models.Q(licenses__license_product__slug__iexact=product)
            )
            if product.isdigit():
                product_filter |= models.Q(licenses__license_product_id=int(product))
            queryset = queryset.filter(product_filter)

        return (
            queryset.distinct()
            .prefetch_related(
                Prefetch(
                    "memberships",
                    queryset=OrganizationMembership.objects.select_related("user")
                    .filter(is_active=True)
                    .order_by("role", "pk"),
                    to_attr="admin_memberships",
                ),
                Prefetch(
                    "licenses",
                    queryset=License.objects.select_related("license_product").order_by(
                        "expires_on", "pk"
                    ),
                    to_attr="admin_licenses",
                ),
            )
            .order_by("name", "pk")
        )

    @classmethod
    def summary(cls):
        today = timezone.localdate()
        active_totals = License.objects.filter(
            status__in=cls.ACTIVE_STATUSES
        ).aggregate(total=models.Sum("used_capacity"))
        expiring_totals = License.objects.filter(
            status__in=cls.ACTIVE_STATUSES,
            expires_on__range=(today, today + timedelta(days=60)),
        ).aggregate(total=models.Sum("used_capacity"))
        return {
            "organizations_with_licenses": Organization.objects.filter(
                licenses__isnull=False
            ).distinct().count(),
            "active_licenses": active_totals["total"] or 0,
            "licenses_expiring_in_60_days": expiring_totals["total"] or 0,
            "payments_in_review": PaymentAttempt.objects.filter(
                status=PaymentAttempt.Status.PENDING
            ).count(),
        }

    @classmethod
    def status_for(cls, licenses):
        licenses = list(licenses)
        today = timezone.localdate()
        if any(
            license.status == License.Status.EXPIRING_SOON
            or (
                license.status == License.Status.ACTIVE
                and license.expires_on
                and license.expires_on <= today + timedelta(days=60)
            )
            for license in licenses
        ):
            return License.Status.EXPIRING_SOON
        for status in (
            License.Status.EXPIRED,
            License.Status.ACTIVE,
            License.Status.PENDING_PAYMENT,
            License.Status.CANCELLED,
        ):
            if any(license.status == status for license in licenses):
                return status
        return License.Status.CANCELLED

    @classmethod
    def organization_row(cls, organization):
        licenses = list(organization.admin_licenses)
        capacity_licenses = [
            license
            for license in licenses
            if license.status != License.Status.CANCELLED
        ]
        owner_membership = next(
            (
                membership
                for membership in organization.admin_memberships
                if membership.role == OrganizationMembership.Role.OWNER
            ),
            None,
        )
        dated_licenses = [
            license for license in capacity_licenses if license.expires_on is not None
        ]
        next_expiry = min(
            (license.expires_on for license in dated_licenses),
            default=None,
        )
        return {
            "id": organization.pk,
            "name": organization.name,
            "owner": (
                {
                    "name": cls._display_name(owner_membership.user),
                    "email": owner_membership.user.email,
                }
                if owner_membership
                else None
            ),
            "license_count": len(licenses),
            "used_capacity": sum(
                license.used_capacity for license in capacity_licenses
            ),
            "total_capacity": sum(license.capacity for license in capacity_licenses),
            "next_expiry": next_expiry,
            "status": cls.status_for(licenses),
        }

    @staticmethod
    def event_message(event):
        metadata = event.metadata or {}
        license_name = event.license.name if event.license_id else "Organization"
        messages = {
            LicenseEvent.Type.PROVISIONED: (
                f"{license_name} activated with capacity "
                f"{metadata.get('capacity', 0)}."
            ),
            LicenseEvent.Type.RENEWED: (
                f"{license_name} renewed through "
                f"{metadata.get('new_expiry', 'the next term')}."
            ),
            LicenseEvent.Type.EXPIRED: f"{license_name} expired.",
            LicenseEvent.Type.NOTIFICATION_SENT: metadata.get(
                "message", "License notification sent."
            ),
            LicenseEvent.Type.INVITATION_SENT: (
                f"License Manager invitation sent to {metadata.get('email', '')}."
            ),
            LicenseEvent.Type.INVITATION_ACCEPTED: (
                "License Manager invitation accepted."
            ),
            LicenseEvent.Type.INVITATION_REVOKED: (
                "License Manager invitation revoked."
            ),
            LicenseEvent.Type.ADJUSTED: metadata.get(
                "reason", "License manually adjusted."
            ),
            LicenseEvent.Type.ALLOCATED: (
                f"{metadata.get('quantity', 0)} product license(s) allocated."
            ),
            LicenseEvent.Type.ALLOCATION_RELEASED: (
                f"{metadata.get('quantity', 0)} product license(s) released."
            ),
        }
        return messages.get(event.event_type, event.get_event_type_display())

    @classmethod
    def event_row(cls, event):
        return {
            "id": event.pk,
            "kind": event.event_type,
            "message": cls.event_message(event),
            "actor_name": (
                cls._display_name(event.actor) if event.actor_id else "System"
            ),
            "license_number": (
                event.license.license_number if event.license_id else None
            ),
            "metadata": event.metadata,
            "created_at": event.occurred_at,
        }

    @staticmethod
    def event_queryset(organization):
        return organization.license_events.select_related(
            "actor", "license"
        ).order_by("-occurred_at", "-pk")

    @classmethod
    def detail(cls, organization):
        memberships = list(
            organization.memberships.select_related("user").filter(is_active=True)
        )
        owner_membership = next(
            (
                membership
                for membership in memberships
                if membership.role == OrganizationMembership.Role.OWNER
            ),
            None,
        )
        licenses = list(
            organization.licenses.select_related(
                "license_product", "source_order_item__order"
            ).order_by("expires_on", "pk")
        )
        active_allocations = ProductLicenseAllocation.objects.filter(
            license__organization=organization,
            status=ProductLicenseAllocation.Status.ACTIVE,
        )
        allocation_totals = active_allocations.aggregate(
            licensed_product_count=models.Count("product_id", distinct=True),
            active_quantity=models.Sum("quantity"),
        )
        current_licenses = [
            license
            for license in licenses
            if license.status != License.Status.CANCELLED
        ]
        starts_on = min(
            (
                license.starts_on
                for license in current_licenses
                if license.starts_on is not None
            ),
            default=None,
        )
        expires_on = min(
            (
                license.expires_on
                for license in current_licenses
                if license.expires_on is not None
            ),
            default=None,
        )
        recent_events = cls.event_queryset(organization)[:20]
        return {
            "organization": {
                "id": organization.pk,
                "name": organization.name,
                "owner": (
                    {
                        "name": cls._display_name(owner_membership.user),
                        "email": owner_membership.user.email,
                    }
                    if owner_membership
                    else None
                ),
                "license_manager_count": sum(
                    membership.role == OrganizationMembership.Role.LICENSE_MANAGER
                    for membership in memberships
                ),
            },
            "summary": {
                "subscription_starts_on": starts_on,
                "subscription_expires_on": expires_on,
                "licensed_product_count": (
                    allocation_totals["licensed_product_count"] or 0
                ),
                "active_quantity": allocation_totals["active_quantity"] or 0,
                "status": cls.status_for(current_licenses),
            },
            "licenses": [
                ClientLicenseDetailService.serialize_license(license)
                for license in licenses
            ],
            "notifications": {
                "renewal_reminder_scheduled_for": (
                    expires_on - timedelta(days=60) if expires_on else None
                ),
                "renewal_invoice_status": "not_issued",
            },
            "events": [cls.event_row(event) for event in recent_events],
            "permissions": {
                "can_adjust": True,
                "can_send_renewal_invoice": True,
                "can_send_notification": True,
            },
        }


class AdminLicenseNotificationService:
    @classmethod
    @transaction.atomic
    def send(cls, *, organization, actor, title, message, license=None):
        if not actor or not actor.is_authenticated or not actor.is_staff:
            raise ValidationError("Only staff can send organization notifications.")
        if license and license.organization_id != organization.pk:
            raise ValidationError({"license_number": "License not found."})

        recipients = [
            membership.user
            for membership in organization.memberships.select_related("user").filter(
                is_active=True,
                user__is_active=True,
            )
        ]
        if not recipients:
            raise ValidationError("The organization has no active recipients.")

        UserNotification.objects.bulk_create(
            [
                UserNotification(
                    recipient=recipient,
                    title=title,
                    message=message,
                    url="/account?tab=licenses",
                )
                for recipient in recipients
            ]
        )
        return LicenseLifecycleService.record_event(
            organization=organization,
            license=license,
            event_type=LicenseEvent.Type.NOTIFICATION_SENT,
            actor=actor,
            metadata={
                "manual": True,
                "title": title,
                "message": message,
                "recipient_ids": [recipient.pk for recipient in recipients],
            },
        )
