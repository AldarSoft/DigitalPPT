from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from html import escape
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import models, transaction
from django.utils import timezone

from common.email_delivery import send_application_email
from licensing.models import (
    License,
    LicenseEvent,
    LicenseOrderItemProvisioning,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    ProductLicenseAllocation,
)
from licensing.permissions import OrganizationAccessPolicy


@dataclass(frozen=True)
class ProductQuantity:
    product: object
    quantity: int


@dataclass(frozen=True)
class LicenseCapacitySlot:
    license: License
    available_capacity: int
    covered_quantity: int


@dataclass(frozen=True)
class LicenseCapacityRequirement:
    license_product: object
    product_quantities: tuple[ProductQuantity, ...]
    requested_quantity: int
    total_capacity: int
    used_capacity: int
    available_capacity: int
    covered_quantity: int
    uncovered_quantity: int
    required_license_units: int
    coverage_plan: tuple[LicenseCapacitySlot, ...]


class ProductLicenseCompatibilityService:
    @staticmethod
    def required_license_product(product):
        if product.licensing_role in {
            product.LicensingRole.STANDARD,
            product.LicensingRole.LICENSE_PRODUCT,
        }:
            return None
        if product.licensing_role != product.LicensingRole.LICENSED_PRODUCT:
            raise ValidationError({"product": "Unknown product licensing role."})

        license_product = product.required_license_product
        if not license_product:
            raise ValidationError(
                {"product": "This licensed product has no compatible license product."}
            )
        if license_product.licensing_role != license_product.LicensingRole.LICENSE_PRODUCT:
            raise ValidationError(
                {"product": "The configured compatibility target is not a license product."}
            )
        if not license_product.license_capacity or not license_product.license_term_days:
            raise ValidationError(
                {"product": "The compatible license product has incomplete capacity data."}
            )
        return license_product

    @classmethod
    def are_compatible(cls, *, product, license_product):
        return cls.required_license_product(product) == license_product


class LicenseCapacityService:
    ELIGIBLE_STATUSES = (License.Status.ACTIVE, License.Status.EXPIRING_SOON)

    @classmethod
    def eligible_licenses(
        cls,
        *,
        organization,
        license_product,
        on_date=None,
        lock=False,
    ):
        if organization is None:
            return License.objects.none()
        on_date = on_date or timezone.localdate()
        queryset = License.objects.filter(
            organization=organization,
            license_product=license_product,
            status__in=cls.ELIGIBLE_STATUSES,
        ).filter(models.Q(expires_on__isnull=True) | models.Q(expires_on__gte=on_date))
        if lock:
            queryset = queryset.select_for_update()
        return queryset.order_by(
            models.F("expires_on").asc(nulls_last=True),
            "created_at",
            "pk",
        )

    @classmethod
    def lookup(
        cls,
        *,
        organization,
        license_product,
        requested_quantity,
        product_quantities=(),
        on_date=None,
        lock=False,
    ):
        if requested_quantity < 0:
            raise ValidationError({"quantity": "Requested quantity cannot be negative."})
        if license_product.licensing_role != license_product.LicensingRole.LICENSE_PRODUCT:
            raise ValidationError({"license_product": "Capacity lookup requires a license product."})
        supplied_capacity = license_product.license_capacity
        if not supplied_capacity:
            raise ValidationError(
                {"license_product": "The license product must supply positive capacity."}
            )

        licenses = list(
            cls.eligible_licenses(
                organization=organization,
                license_product=license_product,
                on_date=on_date,
                lock=lock,
            )
        )
        total_capacity = sum(item.capacity for item in licenses)
        used_capacity = sum(item.used_capacity for item in licenses)
        available_capacity = sum(item.available_capacity for item in licenses)
        covered_quantity = min(requested_quantity, available_capacity)
        uncovered_quantity = requested_quantity - covered_quantity
        required_license_units = (
            (uncovered_quantity + supplied_capacity - 1) // supplied_capacity
            if uncovered_quantity
            else 0
        )

        remaining = covered_quantity
        coverage_plan = []
        for license in licenses:
            available = license.available_capacity
            covered = min(remaining, available)
            coverage_plan.append(
                LicenseCapacitySlot(
                    license=license,
                    available_capacity=available,
                    covered_quantity=covered,
                )
            )
            remaining -= covered

        return LicenseCapacityRequirement(
            license_product=license_product,
            product_quantities=tuple(product_quantities),
            requested_quantity=requested_quantity,
            total_capacity=total_capacity,
            used_capacity=used_capacity,
            available_capacity=available_capacity,
            covered_quantity=covered_quantity,
            uncovered_quantity=uncovered_quantity,
            required_license_units=required_license_units,
            coverage_plan=tuple(coverage_plan),
        )

    @classmethod
    def for_product(
        cls,
        *,
        organization,
        product,
        requested_quantity,
        on_date=None,
        lock=False,
    ):
        license_product = ProductLicenseCompatibilityService.required_license_product(product)
        if license_product is None:
            return None
        product_quantity = ProductQuantity(product=product, quantity=requested_quantity)
        return cls.lookup(
            organization=organization,
            license_product=license_product,
            requested_quantity=requested_quantity,
            product_quantities=(product_quantity,),
            on_date=on_date,
            lock=lock,
        )

    @classmethod
    def requirements_for_products(
        cls,
        *,
        organization,
        product_quantities,
        on_date=None,
        lock=False,
    ):
        grouped = {}
        for product, quantity in product_quantities:
            if quantity < 0:
                raise ValidationError({"quantity": "Product quantity cannot be negative."})
            if quantity == 0:
                continue
            license_product = ProductLicenseCompatibilityService.required_license_product(product)
            if license_product is None:
                continue
            group = grouped.setdefault(
                license_product.pk,
                {"license_product": license_product, "product_quantities": []},
            )
            group["product_quantities"].append(
                ProductQuantity(product=product, quantity=quantity)
            )

        requirements = []
        for group in grouped.values():
            quantities = tuple(group["product_quantities"])
            requirements.append(
                cls.lookup(
                    organization=organization,
                    license_product=group["license_product"],
                    requested_quantity=sum(item.quantity for item in quantities),
                    product_quantities=quantities,
                    on_date=on_date,
                    lock=lock,
                )
            )
        return tuple(requirements)


@dataclass(frozen=True)
class CartLicenseRequirement:
    capacity: LicenseCapacityRequirement
    provided_license_units: int
    automatic_license_units: int


class CartLicenseService:
    @staticmethod
    def organization_for_user(user, organization_id=None):
        if not user or not user.is_authenticated or user.is_staff:
            return None
        membership = (
            OrganizationMembership.objects.filter(
                user=user,
                is_active=True,
                organization__is_active=True,
            )
            .select_related("organization")
            .order_by(
                models.Case(
                    models.When(
                        role=OrganizationMembership.Role.OWNER,
                        then=models.Value(0),
                    ),
                    default=models.Value(1),
                    output_field=models.IntegerField(),
                ),
                "created_at",
                "pk",
            )
        )
        if organization_id is not None:
            membership = membership.filter(organization_id=organization_id).first()
        else:
            membership = membership.first()
        return membership.organization if membership else None

    @classmethod
    def calculate(
        cls,
        *,
        user,
        product_quantities,
        organization_id=None,
        on_date=None,
        lock=False,
    ):
        organization = cls.organization_for_user(user, organization_id=organization_id)
        aggregated = {}
        for product, quantity in product_quantities:
            if quantity <= 0:
                raise ValidationError({"quantity": "Cart quantities must be greater than zero."})
            current = aggregated.setdefault(product.pk, [product, 0])
            current[1] += quantity

        requirements = LicenseCapacityService.requirements_for_products(
            organization=organization,
            product_quantities=(tuple(item) for item in aggregated.values()),
            on_date=on_date,
            lock=lock,
        )
        provided_units = {
            product.pk: quantity
            for product, quantity in aggregated.values()
            if product.licensing_role == product.LicensingRole.LICENSE_PRODUCT
        }
        results = []
        for capacity in requirements:
            provided = provided_units.get(capacity.license_product.pk, 0)
            automatic = max(0, capacity.required_license_units - provided)
            if automatic and not capacity.license_product.__class__.objects.public().filter(
                pk=capacity.license_product.pk
            ).exists():
                raise ValidationError(
                    {
                        "license_product": (
                            f"{capacity.license_product.name} is required but is not available "
                            "for purchase."
                        )
                    }
                )
            results.append(
                CartLicenseRequirement(
                    capacity=capacity,
                    provided_license_units=provided,
                    automatic_license_units=automatic,
                )
            )
        return organization, tuple(results)

    @classmethod
    def normalize_checkout_items(cls, *, user, items, organization_id=None, lock=False):
        manual_items = []
        for item in items:
            product = item["product"]
            is_stale_automatic_license = (
                item.get("automatic", False)
                and product.licensing_role == product.LicensingRole.LICENSE_PRODUCT
            )
            if not is_stale_automatic_license:
                manual_items.append((product, item["quantity"]))

        organization, requirements = cls.calculate(
            user=user,
            product_quantities=manual_items,
            organization_id=organization_id,
            lock=lock,
        )
        normalized = {}
        for product, quantity in manual_items:
            current = normalized.setdefault(product.pk, [product, 0])
            current[1] += quantity
        for requirement in requirements:
            automatic = requirement.automatic_license_units
            if automatic:
                product = requirement.capacity.license_product
                current = normalized.setdefault(product.pk, [product, 0])
                current[1] += automatic
        return organization, tuple(tuple(item) for item in normalized.values()), requirements


class OrganizationService:
    @staticmethod
    @transaction.atomic
    def create(*, name, owner, billing_email=""):
        name = name.strip()
        if not name:
            raise ValidationError({"name": "An organization name is required."})
        if not owner or not owner.is_authenticated or not owner.is_active:
            raise ValidationError({"owner": "An active owner is required."})
        normalized_billing_email = billing_email.strip().casefold()
        if normalized_billing_email:
            validate_email(normalized_billing_email)
        organization = Organization.objects.create(
            name=name,
            billing_email=normalized_billing_email,
            created_by=owner,
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=owner,
            role=OrganizationMembership.Role.OWNER,
        )
        return organization


class OrganizationSummaryService:
    ACTIVE_LICENSE_STATUSES = (
        License.Status.ACTIVE,
        License.Status.EXPIRING_SOON,
    )

    @staticmethod
    def _display_name(user):
        return user.get_full_name().strip() or user.email or user.get_username()

    @classmethod
    def membership_for_user(cls, user, organization_id=None):
        if not user or not user.is_authenticated:
            return None
        memberships = (
            OrganizationMembership.objects.select_related("organization")
            .filter(user=user, is_active=True, organization__is_active=True)
            .order_by(
                models.Case(
                    models.When(
                        role=OrganizationMembership.Role.OWNER,
                        then=models.Value(0),
                    ),
                    default=models.Value(1),
                ),
                "organization__name",
                "pk",
            )
        )
        if organization_id is not None:
            return memberships.filter(organization_id=organization_id).first()
        return memberships.first()

    @classmethod
    def workspaces_for_user(cls, user):
        if not user or not user.is_authenticated:
            return {"organizations": [], "default_organization_id": None}
        memberships = list(
            OrganizationMembership.objects.select_related("organization")
            .filter(user=user, is_active=True, organization__is_active=True)
            .order_by(
                models.Case(
                    models.When(
                        role=OrganizationMembership.Role.OWNER,
                        then=models.Value(0),
                    ),
                    default=models.Value(1),
                ),
                "organization__name",
                "pk",
            )
        )
        return {
            "organizations": [
                {
                    "id": membership.organization_id,
                    "name": membership.organization.name,
                    "role": membership.role,
                }
                for membership in memberships
            ],
            "default_organization_id": memberships[0].organization_id if memberships else None,
        }

    @classmethod
    def for_user(cls, user, organization_id=None):
        membership = cls.membership_for_user(user, organization_id=organization_id)
        if membership is None:
            return None

        organization = membership.organization
        licenses = License.objects.filter(organization=organization).exclude(
            status=License.Status.CANCELLED
        )
        totals = licenses.aggregate(
            license_count=models.Count("pk"),
            active_license_count=models.Count(
                "pk",
                filter=models.Q(status__in=cls.ACTIVE_LICENSE_STATUSES),
            ),
            expired_license_count=models.Count(
                "pk",
                filter=models.Q(status=License.Status.EXPIRED),
            ),
            expiring_soon_count=models.Count(
                "pk",
                filter=models.Q(status=License.Status.EXPIRING_SOON),
            ),
            total_capacity=models.Sum("capacity"),
            used_capacity=models.Sum("used_capacity"),
        )
        total_capacity = totals["total_capacity"] or 0
        used_capacity = totals["used_capacity"] or 0
        today = timezone.localdate()
        next_license = (
            licenses.filter(expires_on__gte=today)
            .exclude(expires_on__isnull=True)
            .order_by("expires_on", "pk")
            .first()
        )
        owner_membership = (
            organization.memberships.select_related("user")
            .filter(
                role=OrganizationMembership.Role.OWNER,
                is_active=True,
            )
            .first()
        )
        active_manager_count = organization.memberships.filter(
            role=OrganizationMembership.Role.LICENSE_MANAGER,
            is_active=True,
        ).count()
        pending_invitation_count = organization.invitations.filter(
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).count()

        return {
            "organization": {
                "id": organization.pk,
                "public_id": str(organization.public_id),
                "name": organization.name,
                "billing_email": organization.billing_email,
                "current_user_role": membership.role,
            },
            "summary": {
                "license_count": totals["license_count"],
                "active_license_count": totals["active_license_count"],
                "expiring_soon_count": totals["expiring_soon_count"],
                "expired_license_count": totals["expired_license_count"],
                "total_capacity": total_capacity,
                "used_capacity": used_capacity,
                "available_capacity": total_capacity - used_capacity,
                "next_expiry": next_license.expires_on if next_license else None,
                "next_expiry_remaining_days": (
                    next_license.calculate_remaining_days(today)
                    if next_license
                    else None
                ),
            },
            "team": {
                "owner": (
                    {
                        "name": cls._display_name(owner_membership.user),
                        "email": owner_membership.user.email,
                    }
                    if owner_membership
                    else None
                ),
                "license_manager_count": active_manager_count,
                "pending_invitation_count": pending_invitation_count,
            },
        }


class OrganizationLicenseListService:
    @classmethod
    def for_user(cls, user, organization_id=None):
        organization_summary = OrganizationSummaryService.for_user(
            user,
            organization_id=organization_id,
        )
        if organization_summary is None:
            return None

        organization_data = organization_summary["organization"]
        summary_data = organization_summary["summary"]
        licenses = (
            License.objects.select_related("license_product")
            .filter(organization_id=organization_data["id"])
            .exclude(status=License.Status.CANCELLED)
            .order_by("expires_on", "created_at", "pk")
        )
        license_rows = []
        for license in licenses:
            capacity_percentage = (
                round((license.used_capacity / license.capacity) * 100)
                if license.capacity
                else 0
            )
            license_rows.append(
                {
                    "id": license.pk,
                    "license_number": license.license_number,
                    "name": license.name,
                    "plan_name": license.license_product.name,
                    "plan_sku": license.license_product.sku,
                    "status": license.status,
                    "capacity": license.capacity,
                    "used_capacity": license.used_capacity,
                    "available_capacity": license.available_capacity,
                    "capacity_percentage": capacity_percentage,
                    "starts_on": license.starts_on,
                    "expires_on": license.expires_on,
                    "renews_on": license.renews_on,
                    "remaining_days": license.remaining_days,
                }
            )

        renewal_request = (
            LicenseEvent.objects.filter(
                organization_id=organization_data["id"],
                event_type=LicenseEvent.Type.NOTIFICATION_SENT,
                metadata__notification_type="renewal_invoice",
            )
            .order_by("-created_at", "-pk")
            .values("created_at")
            .first()
        )
        has_current_renewal_need = licenses.filter(
            status__in=(License.Status.EXPIRING_SOON, License.Status.EXPIRED),
        ).exists()

        return {
            "organization": {
                "id": organization_data["id"],
                "public_id": organization_data["public_id"],
                "name": organization_data["name"],
                "role": organization_data["current_user_role"],
            },
            "summary": summary_data,
            "licenses": license_rows,
            "renewal_request": {
                # Notification history is retained, but the client-page banner
                # must reflect the current license state rather than an old
                # reminder that staff has since resolved.
                "issued": bool(renewal_request and has_current_renewal_need),
                "issued_at": (
                    renewal_request["created_at"]
                    if renewal_request and has_current_renewal_need
                    else None
                ),
            },
        }


class ClientLicenseDetailService:
    @staticmethod
    def _source_order(order_item):
        if order_item is None:
            return None
        return {
            "order_number": order_item.order.order_number,
            "ordered_at": order_item.order.created_at,
        }

    @classmethod
    def serialize_license(cls, license):
        allocations = (
            ProductLicenseAllocation.objects.select_related(
                "product",
                "order_item__order",
            )
            .filter(
                license=license,
                status=ProductLicenseAllocation.Status.ACTIVE,
            )
            .order_by("created_at", "pk")
        )
        return {
            "license_number": license.license_number,
            "name": license.name,
            "plan_name": license.license_product.name,
            "plan_sku": license.license_product.sku,
            "status": license.status,
            "capacity": license.capacity,
            "used_capacity": license.used_capacity,
            "available_capacity": license.available_capacity,
            "starts_on": license.starts_on,
            "expires_on": license.expires_on,
            "renews_on": license.renews_on,
            "remaining_days": license.remaining_days,
            "subscription": {
                "term_days": license.license_product.license_term_days,
                "starts_on": license.starts_on,
                "expires_on": license.expires_on,
                "renews_on": license.renews_on,
                "remaining_days": license.remaining_days,
                "source_order": cls._source_order(license.source_order_item),
            },
            "allocations": [
                {
                    "id": allocation.pk,
                    "product": {
                        "id": allocation.product_id,
                        "name": allocation.product.name,
                        "sku": allocation.product.sku,
                    },
                    "quantity": allocation.quantity,
                    "source_order": cls._source_order(allocation.order_item),
                }
                for allocation in allocations
            ],
        }

    @classmethod
    def for_user(cls, *, user, license_number, organization_id=None):
        membership = OrganizationSummaryService.membership_for_user(
            user,
            organization_id=organization_id,
        )
        if membership is None:
            return None

        license = (
            License.objects.select_related(
                "license_product",
                "source_order_item__order",
            )
            .filter(
                organization=membership.organization,
                license_number=license_number,
            )
            .first()
        )
        if license is None:
            return None

        return cls.serialize_license(license)


class OrganizationTeamService:
    @classmethod
    def for_user(cls, user, organization_id=None):
        membership = OrganizationSummaryService.membership_for_user(
            user,
            organization_id=organization_id,
        )
        if membership is None:
            return None

        organization = membership.organization
        memberships = list(
            organization.memberships.select_related("user")
            .filter(is_active=True)
            .order_by("role", "user__first_name", "user__email", "pk")
        )
        owner_membership = next(
            (
                item
                for item in memberships
                if item.role == OrganizationMembership.Role.OWNER
            ),
            None,
        )
        manager_memberships = [
            item
            for item in memberships
            if item.role == OrganizationMembership.Role.LICENSE_MANAGER
        ]
        pending_invitations = organization.invitations.filter(
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at", "pk")
        can_manage_team = OrganizationAccessPolicy.can_manage_team(
            user=user,
            organization=organization,
        )

        return {
            "organization": {
                "id": organization.pk,
                "name": organization.name,
            },
            "current_user_role": membership.role,
            "owner": (
                {
                    "id": owner_membership.user_id,
                    "name": OrganizationSummaryService._display_name(
                        owner_membership.user
                    ),
                    "email": owner_membership.user.email,
                }
                if owner_membership
                else None
            ),
            "license_managers": [
                {
                    "membership_id": item.pk,
                    "name": OrganizationSummaryService._display_name(item.user),
                    "email": item.user.email,
                    "role": item.role,
                    "status": "active",
                }
                for item in manager_memberships
            ],
            "pending_invitations": [
                {
                    "invitation_id": invitation.pk,
                    "email": invitation.email,
                    "role": invitation.role,
                    "status": invitation.status,
                    "expires_at": invitation.expires_at,
                }
                for invitation in pending_invitations
            ],
            "permissions": {
                "can_invite": can_manage_team,
                "can_revoke_manager": can_manage_team,
                "can_transfer_ownership": can_manage_team,
            },
        }


class OrganizationOwnershipService:
    @classmethod
    @transaction.atomic
    def transfer(cls, *, organization, target_membership_id, transferred_by):
        organization = Organization.objects.select_for_update().get(pk=organization.pk)
        if not OrganizationAccessPolicy.can_manage_team(
            user=transferred_by,
            organization=organization,
        ):
            raise PermissionDenied(
                "Only the Organization Owner can transfer organization ownership."
            )

        current_owner = OrganizationMembership.objects.select_for_update().get(
            organization=organization,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        target = (
            OrganizationMembership.objects.select_for_update()
            .select_related("user")
            .filter(
                pk=target_membership_id,
                organization=organization,
                role=OrganizationMembership.Role.LICENSE_MANAGER,
                is_active=True,
            )
            .first()
        )
        if target is None:
            raise ValidationError(
                {
                    "membership_id": (
                        "Choose an active License Manager as the new Organization Owner."
                    )
                }
            )

        current_owner.role = OrganizationMembership.Role.LICENSE_MANAGER
        current_owner.save(update_fields=("role", "updated_at"))
        target.role = OrganizationMembership.Role.OWNER
        target.save(update_fields=("role", "updated_at"))
        LicenseEvent.objects.create(
            organization=organization,
            event_type=LicenseEvent.Type.OWNERSHIP_TRANSFERRED,
            actor=transferred_by,
            metadata={
                "previous_owner_id": current_owner.user_id,
                "previous_owner_email": current_owner.user.email,
                "new_owner_id": target.user_id,
                "new_owner_email": target.user.email,
            },
        )
        return target


class InvitationService:
    DEFAULT_EXPIRY = timedelta(days=7)

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def accept_url(token):
        return f"{settings.FRONTEND_URL.rstrip('/')}/invite?token={quote(token, safe='')}"

    @staticmethod
    def send_email(*, invitation, token):
        accept_url = InvitationService.accept_url(token)
        organization_name = invitation.organization.name
        subject = f"Invitation to manage licenses for {organization_name}"
        text_body = (
            f"You have been invited to become a License Manager for {organization_name}.\n\n"
            f"Sign in with {invitation.email} and accept the invitation:\n{accept_url}\n\n"
            f"This invitation expires on {timezone.localtime(invitation.expires_at):%d %b %Y %H:%M}."
        )
        html_body = (
            f"<p>You have been invited to become a <strong>License Manager</strong> for "
            f"<strong>{escape(organization_name)}</strong>.</p>"
            f"<p>Sign in with <strong>{escape(invitation.email)}</strong> and "
            f"<a href=\"{escape(accept_url, quote=True)}\">accept the invitation</a>.</p>"
            f"<p>This invitation expires on "
            f"{timezone.localtime(invitation.expires_at):%d %b %Y %H:%M}.</p>"
        )
        send_application_email(
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            recipients=[invitation.email],
        )

    @classmethod
    @transaction.atomic
    def issue(cls, *, organization, email, invited_by, expires_in=None):
        if not OrganizationAccessPolicy.can_manage_team(
            user=invited_by,
            organization=organization,
        ):
            raise PermissionDenied("Only the Organization Owner can invite License Managers.")

        normalized_email = email.strip().casefold()
        if not normalized_email:
            raise ValidationError({"email": "An email address is required."})
        validate_email(normalized_email)

        User = get_user_model()
        existing_user = User.objects.filter(email__iexact=normalized_email).first()
        if existing_user and OrganizationMembership.objects.filter(
            organization=organization,
            user=existing_user,
            is_active=True,
        ).exists():
            raise ValidationError({"email": "This user already belongs to the organization."})

        Organization.objects.select_for_update().get(pk=organization.pk)
        now = timezone.now()
        previous_invitations = list(OrganizationInvitation.objects.filter(
            organization=organization,
            email__iexact=normalized_email,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ))
        OrganizationInvitation.objects.filter(
            pk__in=[invitation.pk for invitation in previous_invitations]
        ).update(revoked_at=now, updated_at=now)
        for previous in previous_invitations:
            LicenseEvent.objects.create(
                organization=organization,
                invitation=previous,
                event_type=LicenseEvent.Type.INVITATION_REVOKED,
                actor=invited_by,
                metadata={"reason": "reissued"},
            )

        raw_token = secrets.token_urlsafe(32)
        invitation = OrganizationInvitation.objects.create(
            organization=organization,
            email=normalized_email,
            role=OrganizationMembership.Role.LICENSE_MANAGER,
            token_hash=cls.hash_token(raw_token),
            expires_at=now + (expires_in or cls.DEFAULT_EXPIRY),
            invited_by=invited_by,
        )
        LicenseEvent.objects.create(
            organization=organization,
            invitation=invitation,
            event_type=LicenseEvent.Type.INVITATION_SENT,
            actor=invited_by,
            metadata={"email": normalized_email, "role": invitation.role},
        )
        cls.send_email(invitation=invitation, token=raw_token)
        return invitation, raw_token

    @classmethod
    @transaction.atomic
    def accept(cls, *, token, user):
        if not user or not user.is_authenticated or not user.is_active:
            raise PermissionDenied("Sign in with an active account to accept this invitation.")
        token_hash = cls.hash_token(token)
        try:
            invitation = (
                OrganizationInvitation.objects.select_for_update()
                .select_related("organization")
                .get(token_hash=token_hash)
            )
        except OrganizationInvitation.DoesNotExist as exc:
            raise ValidationError({"token": "This invitation is invalid."}) from exc

        if invitation.accepted_at:
            if invitation.accepted_by_id == user.id:
                return OrganizationMembership.objects.get(
                    organization=invitation.organization,
                    user=user,
                )
            raise ValidationError({"token": "This invitation has already been accepted."})
        if invitation.revoked_at:
            raise ValidationError({"token": "This invitation has been revoked."})
        if invitation.expires_at <= timezone.now():
            raise ValidationError({"token": "This invitation has expired."})
        if invitation.email.casefold() != user.email.casefold():
            raise PermissionDenied("Sign in with the email address that received this invitation.")

        membership, created = OrganizationMembership.objects.get_or_create(
            organization=invitation.organization,
            user=user,
            defaults={
                "role": OrganizationMembership.Role.LICENSE_MANAGER,
                "invited_by": invitation.invited_by,
            },
        )
        if not created and membership.role != OrganizationMembership.Role.OWNER:
            membership.role = OrganizationMembership.Role.LICENSE_MANAGER
            membership.is_active = True
            membership.invited_by = invitation.invited_by
            membership.save(
                update_fields=["role", "is_active", "invited_by", "updated_at"]
            )

        invitation.accepted_at = timezone.now()
        invitation.accepted_by = user
        invitation.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
        LicenseEvent.objects.create(
            organization=invitation.organization,
            invitation=invitation,
            event_type=LicenseEvent.Type.INVITATION_ACCEPTED,
            actor=user,
            metadata={"membership_id": membership.pk},
        )
        return membership

    @classmethod
    @transaction.atomic
    def resend(cls, *, invitation, resent_by):
        locked = (
            OrganizationInvitation.objects.select_for_update()
            .select_related("organization")
            .get(pk=invitation.pk)
        )
        if not OrganizationAccessPolicy.can_manage_team(
            user=resent_by,
            organization=locked.organization,
        ):
            raise PermissionDenied("Only the Organization Owner can resend invitations.")
        if locked.accepted_at:
            raise ValidationError("Accepted invitations cannot be resent.")
        if locked.revoked_at:
            raise ValidationError("Revoked invitations cannot be resent.")
        return cls.issue(
            organization=locked.organization,
            email=locked.email,
            invited_by=resent_by,
        )

    @staticmethod
    @transaction.atomic
    def revoke(*, invitation, revoked_by):
        locked = OrganizationInvitation.objects.select_for_update().get(pk=invitation.pk)
        if not OrganizationAccessPolicy.can_manage_team(
            user=revoked_by,
            organization=locked.organization,
        ):
            raise PermissionDenied("Only the Organization Owner can revoke invitations.")
        if locked.accepted_at:
            raise ValidationError("Accepted invitations cannot be revoked.")
        if not locked.revoked_at:
            locked.revoked_at = timezone.now()
            locked.save(update_fields=["revoked_at", "updated_at"])
            LicenseEvent.objects.create(
                organization=locked.organization,
                invitation=locked,
                event_type=LicenseEvent.Type.INVITATION_REVOKED,
                actor=revoked_by,
            )
        return locked


class LicenseLifecycleService:
    @staticmethod
    def record_event(*, organization, event_type, license=None, actor=None, metadata=None):
        return LicenseEvent.objects.create(
            organization=organization,
            license=license,
            event_type=event_type,
            actor=actor,
            metadata=metadata or {},
        )

    @classmethod
    @transaction.atomic
    def provision(
        cls,
        *,
        organization,
        license_product,
        source_order_item=None,
        actor=None,
        starts_on=None,
        name="",
    ):
        if license_product.licensing_role != license_product.LicensingRole.LICENSE_PRODUCT:
            raise ValidationError(
                {"license_product": "Provisioning requires a license product."}
            )
        if not license_product.license_capacity or not license_product.license_term_days:
            raise ValidationError(
                {"license_product": "The license product needs capacity and a term."}
            )

        starts_on = starts_on or timezone.localdate()
        expires_on = starts_on + timedelta(days=license_product.license_term_days - 1)
        license = License(
            organization=organization,
            license_product=license_product,
            name=name.strip() or license_product.name,
            status=License.Status.ACTIVE,
            capacity=license_product.license_capacity,
            starts_on=starts_on,
            expires_on=expires_on,
            renews_on=expires_on + timedelta(days=1),
            source_order_item=source_order_item,
        )
        license.full_clean()
        license.save()
        cls.record_event(
            organization=organization,
            license=license,
            event_type=LicenseEvent.Type.PROVISIONED,
            actor=actor,
            metadata={
                "capacity": license.capacity,
                "license_product_id": license_product.pk,
                "source_order_item_id": source_order_item.pk if source_order_item else None,
            },
        )
        return license

    @classmethod
    @transaction.atomic
    def allocate(cls, *, license, product, order_item, quantity, actor=None):
        from orders.models import OrderItem

        locked_order_item = OrderItem.objects.select_for_update().get(pk=order_item.pk)
        already_allocated = (
            ProductLicenseAllocation.objects.filter(
                order_item=locked_order_item,
                status=ProductLicenseAllocation.Status.ACTIVE,
            ).aggregate(total=models.Sum("quantity"))["total"]
            or 0
        )
        if already_allocated + quantity > locked_order_item.quantity:
            raise ValidationError(
                {"quantity": "Allocations cannot exceed the source order-item quantity."}
            )

        allocation = ProductLicenseAllocation(
            license=license,
            product=product,
            order_item=locked_order_item,
            quantity=quantity,
        )
        allocation.save()
        cls.record_event(
            organization=license.organization,
            license=license,
            event_type=LicenseEvent.Type.ALLOCATED,
            actor=actor,
            metadata={
                "allocation_id": allocation.pk,
                "product_id": product.pk,
                "order_item_id": order_item.pk,
                "quantity": quantity,
            },
        )
        return allocation

    @classmethod
    @transaction.atomic
    def release_allocation(cls, *, allocation, actor=None, reason=""):
        locked = ProductLicenseAllocation.objects.select_for_update().get(pk=allocation.pk)
        if locked.status == ProductLicenseAllocation.Status.RELEASED:
            return locked
        license = License.objects.select_for_update().get(pk=locked.license_id)
        if license.used_capacity < locked.quantity:
            raise ValidationError("License used capacity is inconsistent with its allocations.")

        released_at = timezone.now()
        ProductLicenseAllocation.objects.filter(pk=locked.pk).update(
            status=ProductLicenseAllocation.Status.RELEASED,
            released_at=released_at,
            updated_at=released_at,
        )
        license.used_capacity -= locked.quantity
        license.save(update_fields=["used_capacity", "updated_at"])
        locked.refresh_from_db()
        cls.record_event(
            organization=license.organization,
            license=license,
            event_type=LicenseEvent.Type.ALLOCATION_RELEASED,
            actor=actor,
            metadata={
                "allocation_id": locked.pk,
                "quantity": locked.quantity,
                "reason": reason.strip(),
            },
        )
        return locked

    @classmethod
    @transaction.atomic
    def renew(
        cls,
        *,
        license,
        actor=None,
        term_days=None,
        source_order_item=None,
    ):
        locked = License.objects.select_for_update().select_related("license_product").get(
            pk=license.pk
        )
        days = term_days or locked.license_product.license_term_days
        if not days or days <= 0:
            raise ValidationError({"term_days": "Renewal term must be greater than zero."})
        previous_expiry = locked.expires_on
        base_date = max(timezone.localdate(), previous_expiry or timezone.localdate())
        locked.expires_on = base_date + timedelta(days=days)
        locked.renews_on = locked.expires_on + timedelta(days=1)
        locked.status = License.Status.ACTIVE
        locked.save(update_fields=["expires_on", "renews_on", "status", "updated_at"])
        cls.record_event(
            organization=locked.organization,
            license=locked,
            event_type=LicenseEvent.Type.RENEWED,
            actor=actor,
            metadata={
                "previous_expiry": previous_expiry.isoformat() if previous_expiry else None,
                "new_expiry": locked.expires_on.isoformat(),
                "term_days": days,
                "source_order_item_id": (
                    source_order_item.pk if source_order_item else None
                ),
            },
        )
        return locked

    @classmethod
    @transaction.atomic
    def adjust(cls, *, license, actor, reason, capacity=None, status=None):
        if not actor or not actor.is_authenticated or not actor.is_staff:
            raise PermissionDenied("Only staff can manually adjust licenses.")
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError({"reason": "A reason is required for manual adjustments."})
        if capacity is None and status is None:
            raise ValidationError(
                {"adjustment": "Provide a capacity or status adjustment."}
            )

        locked = License.objects.select_for_update().get(pk=license.pk)
        previous = {
            "capacity": locked.capacity,
            "status": locked.status,
        }
        if capacity is not None:
            if capacity <= 0:
                raise ValidationError({"capacity": "Capacity must be greater than zero."})
            if capacity < locked.used_capacity:
                raise ValidationError(
                    {
                        "capacity": (
                            "Capacity cannot be lower than the currently allocated quantity."
                        )
                    }
                )
            locked.capacity = capacity
        if status is not None:
            if status not in License.Status.values:
                raise ValidationError({"status": "Select a valid license status."})
            locked.status = status

        current = {
            "capacity": locked.capacity,
            "status": locked.status,
        }
        if current == previous:
            raise ValidationError({"adjustment": "The adjustment does not change the license."})
        locked.full_clean()
        locked.save(update_fields=["capacity", "status", "updated_at"])
        cls.record_event(
            organization=locked.organization,
            license=locked,
            event_type=LicenseEvent.Type.ADJUSTED,
            actor=actor,
            metadata={
                "reason": reason,
                "previous": previous,
                "current": current,
            },
        )
        return locked


class LicenseExpiryService:
    WARNING_DAYS = (60, 30, 7)

    @classmethod
    def _notification_stage(cls, remaining_days):
        if remaining_days < 0:
            return "expired"
        if remaining_days == 0:
            return "expires_today"
        for threshold in reversed(cls.WARNING_DAYS):
            if remaining_days <= threshold:
                return f"expires_in_{threshold}_days"
        return None

    @staticmethod
    def _notification_copy(*, license, remaining_days):
        if remaining_days < 0:
            return (
                f"License {license.license_number} has expired",
                (
                    f"{license.name} expired {abs(remaining_days)} day(s) ago. "
                    "Product access remains available while renewal is arranged."
                ),
            )
        if remaining_days == 0:
            return (
                f"License {license.license_number} expires today",
                f"{license.name} expires today. Please arrange renewal.",
            )
        return (
            f"License {license.license_number} expires in {remaining_days} days",
            f"{license.name} expires on {license.expires_on}. Please arrange renewal.",
        )

    @classmethod
    @transaction.atomic
    def reconcile(cls, *, license, on_date=None):
        from core.models import UserNotification

        on_date = on_date or timezone.localdate()
        locked = (
            License.objects.select_for_update()
            .select_related("organization")
            .get(pk=license.pk)
        )
        remaining_days = locked.calculate_remaining_days(on_date)
        if remaining_days is None or locked.status == License.Status.CANCELLED:
            return locked, False

        target_status = (
            License.Status.EXPIRED
            if remaining_days < 0
            else (
                License.Status.EXPIRING_SOON
                if remaining_days <= max(cls.WARNING_DAYS)
                else License.Status.ACTIVE
            )
        )
        if locked.status != target_status:
            locked.status = target_status
            locked.save(update_fields=["status", "updated_at"])

        expiry_key = locked.expires_on.isoformat()
        if remaining_days < 0 and not LicenseEvent.objects.filter(
            license=locked,
            event_type=LicenseEvent.Type.EXPIRED,
            metadata__expiry=expiry_key,
        ).exists():
            LicenseLifecycleService.record_event(
                organization=locked.organization,
                license=locked,
                event_type=LicenseEvent.Type.EXPIRED,
                metadata={"expiry": expiry_key, "remaining_days": remaining_days},
            )

        stage = cls._notification_stage(remaining_days)
        if not stage:
            return locked, False
        notification_key = f"{locked.pk}:{expiry_key}:{stage}"
        if LicenseEvent.objects.filter(
            license=locked,
            event_type=LicenseEvent.Type.NOTIFICATION_SENT,
            metadata__notification_key=notification_key,
        ).exists():
            return locked, False

        User = get_user_model()
        recipients = User.objects.filter(
            models.Q(
                organization_memberships__organization=locked.organization,
                organization_memberships__is_active=True,
            )
            | models.Q(is_staff=True),
            is_active=True,
        ).distinct()
        title, message = cls._notification_copy(
            license=locked,
            remaining_days=remaining_days,
        )
        recipient_ids = []
        notifications = []
        for recipient in recipients:
            recipient_ids.append(recipient.pk)
            notifications.append(
                UserNotification(
                    recipient=recipient,
                    title=title,
                    message=message,
                    url=(
                        f"/admin/licenses?license={locked.license_number}"
                        if recipient.is_staff
                        else "/account?tab=licenses"
                    ),
                )
            )
        UserNotification.objects.bulk_create(notifications)
        LicenseLifecycleService.record_event(
            organization=locked.organization,
            license=locked,
            event_type=LicenseEvent.Type.NOTIFICATION_SENT,
            metadata={
                "notification_key": notification_key,
                "stage": stage,
                "expiry": expiry_key,
                "remaining_days": remaining_days,
                "recipient_ids": recipient_ids,
            },
        )
        from core.notifications import publish_license_expiry

        transaction.on_commit(
            lambda license_id=locked.pk, days=remaining_days: publish_license_expiry(
                license_id=license_id,
                remaining_days=days,
            )
        )
        return locked, True

    @classmethod
    def reconcile_all(cls, *, on_date=None):
        license_ids = list(
            License.objects.exclude(status=License.Status.CANCELLED).values_list(
                "pk", flat=True
            )
        )
        notified = 0
        for license_id in license_ids:
            _, was_notified = cls.reconcile(
                license=License(pk=license_id),
                on_date=on_date,
            )
            notified += int(was_notified)
        return {"processed": len(license_ids), "notified": notified}



class LicenseRenewalOrderService:
    RENEWAL_WINDOW_DAYS = 60

    @classmethod
    def resolve(cls, *, user, license_number, organization_id=None, lock=False):
        membership = OrganizationSummaryService.membership_for_user(
            user,
            organization_id=organization_id,
        )
        if membership is None:
            raise PermissionDenied("Organization license access is required.")
        licenses = License.objects
        if lock:
            licenses = licenses.select_for_update()
        license = (
            licenses
            .select_related("organization", "license_product")
            .filter(
                organization=membership.organization,
                license_number=license_number,
                status__in=(License.Status.ACTIVE, License.Status.EXPIRING_SOON, License.Status.EXPIRED),
            )
            .first()
        )
        if license is None:
            raise ValidationError({"license": "This license cannot be renewed."})
        if not OrganizationAccessPolicy.can_manage_billing(user=user, organization=license.organization):
            raise PermissionDenied("Only an Owner or License Manager can renew this license.")
        remaining_days = license.calculate_remaining_days(timezone.localdate())
        is_marked_for_renewal = license.status in {
            License.Status.EXPIRING_SOON,
            License.Status.EXPIRED,
        }
        if (
            remaining_days is None
            or (
                remaining_days > cls.RENEWAL_WINDOW_DAYS
                and not is_marked_for_renewal
            )
        ):
            raise ValidationError({"license": "Renewal becomes available within 60 days of expiry."})

        from products.models import Product

        product = Product.objects.select_for_update().public().filter(
            pk=license.license_product_id,
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
        ).first()
        if product is None:
            raise ValidationError({"license": "The renewal product is not currently available for purchase."})
        return license, product

    @classmethod
    def summary(cls, *, user, license_number, organization_id=None):
        license, product = cls.resolve(
            user=user,
            license_number=license_number,
            organization_id=organization_id,
        )
        current_expiry = license.expires_on
        base_date = max(timezone.localdate(), current_expiry or timezone.localdate())
        return {
            "license_number": license.license_number,
            "license_name": license.name,
            "organization_id": license.organization_id,
            "organization_name": license.organization.name,
            "current_expires_on": current_expiry,
            "projected_expires_on": base_date + timedelta(days=product.license_term_days),
            "term_days": product.license_term_days,
            "product_id": product.pk,
            "product_name": product.name,
            "product_sku": product.sku,
            "product_image_url": product.images.order_by("id").values_list("image_url", flat=True).first() or "",
            "amount": product.price_for_quantity(1),
        }


@dataclass(frozen=True)
class PaymentProvisioningResult:
    organization: Organization | None
    created_license_ids: tuple[int, ...]
    renewed_license_ids: tuple[int, ...]
    created_allocation_ids: tuple[int, ...]
    already_completed: bool = False


class PaymentSuccessProvisioningService:
    """Provision paid licensing items inside the payment success transaction."""

    METADATA_KEY = "license_provisioning"

    @staticmethod
    def _organization_name(*, order, purchaser):
        profile = getattr(purchaser, "profile", None)
        company_name = (
            order.company_name.strip()
            or (getattr(profile, "company_name", "") or "").strip()
        )
        if company_name:
            return company_name
        full_name = purchaser.get_full_name().strip()
        if full_name:
            return f"{full_name} Organization"
        identity = purchaser.email or purchaser.get_username()
        return f"{identity.split('@', 1)[0]} Organization"

    @classmethod
    def _result_from_marker(cls, marker):
        organization = None
        organization_id = marker.get("organization_id")
        if organization_id:
            organization = Organization.objects.filter(pk=organization_id).first()
        return PaymentProvisioningResult(
            organization=organization,
            created_license_ids=tuple(marker.get("license_ids", ())),
            renewed_license_ids=tuple(marker.get("renewed_license_ids", ())),
            created_allocation_ids=tuple(marker.get("allocation_ids", ())),
            already_completed=True,
        )

    @classmethod
    @transaction.atomic
    def provision(cls, *, payment_attempt, actor=None):
        from orders.models import Order, OrderItem
        from payments.models import PaymentAttempt

        payment = (
            PaymentAttempt.objects.select_for_update()
            .select_related("order__user", "created_by")
            .get(pk=payment_attempt.pk)
        )
        if payment.status != PaymentAttempt.Status.SUCCEEDED:
            raise ValidationError(
                {"payment": "Licenses can only be provisioned for a successful payment."}
            )

        marker = (payment.metadata or {}).get(cls.METADATA_KEY, {})
        if marker.get("status") == "completed":
            return cls._result_from_marker(marker)

        order = (
            Order.objects.select_for_update()
            .select_related("user", "organization", "renewal_license")
            .prefetch_related("items__product__required_license_product")
            .get(pk=payment.order_id)
        )
        items = list(
            OrderItem.objects.select_for_update()
            .select_related("product__required_license_product")
            .filter(order=order)
            .order_by("pk")
        )
        licensing_items = [
            item
            for item in items
            if item.product_id
            and item.product.licensing_role != item.product.LicensingRole.STANDARD
        ]

        organization = None
        created_licenses = []
        renewed_licenses = []
        created_allocations = []
        if licensing_items:
            purchaser = order.user or (
                payment.created_by
                if payment.created_by and not payment.created_by.is_staff
                else None
            )
            if not purchaser or not purchaser.is_active:
                raise ValidationError(
                    {"organization": "A paid licensing order requires an active purchaser."}
                )

            User = get_user_model()
            purchaser = User.objects.select_for_update().get(pk=purchaser.pk)
            # The checkout organization is authoritative. Falling back keeps
            # legacy orders working until staff associates them in Django Admin.
            organization = order.organization or CartLicenseService.organization_for_user(purchaser)
            if organization is None:
                organization = OrganizationService.create(
                    name=cls._organization_name(order=order, purchaser=purchaser),
                    owner=purchaser,
                    billing_email=order.customer_email or purchaser.email,
                )
            else:
                organization = Organization.objects.select_for_update().get(
                    pk=organization.pk
                )
            if order.organization_id != organization.pk:
                order.organization = organization
                order.save(update_fields=["organization", "updated_at"])

            license_order_items = [
                item
                for item in licensing_items
                if item.product.licensing_role
                == item.product.LicensingRole.LICENSE_PRODUCT
            ]
            licensed_order_items = [
                item
                for item in licensing_items
                if item.product.licensing_role
                == item.product.LicensingRole.LICENSED_PRODUCT
            ]
            for order_item in license_order_items:
                provisioning_record = (
                    LicenseOrderItemProvisioning.objects.select_for_update()
                    .filter(order_item=order_item)
                    .first()
                )
                if provisioning_record:
                    if provisioning_record.organization_id != organization.pk:
                        raise ValidationError(
                            {
                                "order_item": (
                                    "The order item was already provisioned for another "
                                    "organization."
                                )
                            }
                        )
                    created_licenses.extend(
                        License.objects.filter(
                            pk__in=provisioning_record.created_license_ids
                        )
                    )
                    renewed_licenses.extend(
                        License.objects.filter(
                            pk__in=provisioning_record.renewed_license_ids
                        )
                    )
                    continue

                created_start = len(created_licenses)
                renewed_start = len(renewed_licenses)
                existing = list(
                    License.objects.select_for_update()
                    .filter(source_order_item=order_item)
                    .order_by("pk")
                )
                renewal_candidates = []
                if order.renewal_license_id:
                    renewal_candidate = (
                        License.objects.select_for_update()
                        .filter(
                            pk=order.renewal_license_id,
                            organization=organization,
                            license_product=order_item.product,
                            status__in=(
                                License.Status.ACTIVE,
                                License.Status.EXPIRING_SOON,
                                License.Status.EXPIRED,
                            ),
                        )
                        .first()
                    )
                    if renewal_candidate is None:
                        raise ValidationError(
                            {"license": "The selected license is no longer available for renewal."}
                        )
                    renewal_candidates = [renewal_candidate]
                for unit_index in range(len(existing), order_item.quantity):
                    if renewal_candidates:
                        renewed_licenses.append(
                            LicenseLifecycleService.renew(
                                license=renewal_candidates.pop(0),
                                actor=actor or purchaser,
                                source_order_item=order_item,
                            )
                        )
                        continue
                    created_licenses.append(
                        LicenseLifecycleService.provision(
                            organization=organization,
                            license_product=order_item.product,
                            source_order_item=order_item,
                            actor=actor or purchaser,
                            name=(
                                f"{order_item.product.name} {unit_index + 1:02d}"
                                if order_item.quantity > 1
                                else order_item.product.name
                            ),
                        )
                    )
                LicenseOrderItemProvisioning.objects.create(
                    organization=organization,
                    order_item=order_item,
                    operation=(
                        LicenseOrderItemProvisioning.Operation.LICENSE_PURCHASE
                    ),
                    created_license_ids=[
                        license.pk for license in created_licenses[created_start:]
                    ],
                    renewed_license_ids=[
                        license.pk for license in renewed_licenses[renewed_start:]
                    ],
                )

            for order_item in licensed_order_items:
                provisioning_record = (
                    LicenseOrderItemProvisioning.objects.select_for_update()
                    .filter(order_item=order_item)
                    .first()
                )
                if provisioning_record:
                    if provisioning_record.organization_id != organization.pk:
                        raise ValidationError(
                            {
                                "order_item": (
                                    "The order item was already provisioned for another "
                                    "organization."
                                )
                            }
                        )
                    created_allocations.extend(
                        ProductLicenseAllocation.objects.filter(
                            pk__in=provisioning_record.allocation_ids
                        )
                    )
                    continue

                item_allocations = list(
                    ProductLicenseAllocation.objects.select_for_update().filter(
                        order_item=order_item,
                        status=ProductLicenseAllocation.Status.ACTIVE,
                    )
                )
                already_allocated = sum(
                    allocation.quantity for allocation in item_allocations
                )
                remaining = order_item.quantity - already_allocated
                if remaining > 0:
                    compatible_licenses = list(
                        LicenseCapacityService.eligible_licenses(
                            organization=organization,
                            license_product=(
                                order_item.product.required_license_product
                            ),
                            lock=True,
                        )
                    )
                    for license in compatible_licenses:
                        allocation_quantity = min(
                            remaining,
                            license.available_capacity,
                        )
                        if allocation_quantity <= 0:
                            continue
                        allocation = LicenseLifecycleService.allocate(
                            license=license,
                            product=order_item.product,
                            order_item=order_item,
                            quantity=allocation_quantity,
                            actor=actor or purchaser,
                        )
                        created_allocations.append(allocation)
                        item_allocations.append(allocation)
                        remaining -= allocation_quantity
                        if remaining == 0:
                            break

                if remaining:
                    raise ValidationError(
                        {
                            "license_capacity": (
                                f"{remaining} unit(s) of {order_item.product.name} do not "
                                "have paid compatible license capacity."
                            )
                        }
                    )
                LicenseOrderItemProvisioning.objects.create(
                    organization=organization,
                    order_item=order_item,
                    operation=(
                        LicenseOrderItemProvisioning.Operation.PRODUCT_ALLOCATION
                    ),
                    allocation_ids=[
                        allocation.pk for allocation in item_allocations
                    ],
                )

        marker = {
            "status": "completed",
            "organization_id": organization.pk if organization else None,
            "license_ids": [license.pk for license in created_licenses],
            "renewed_license_ids": [license.pk for license in renewed_licenses],
            "allocation_ids": [allocation.pk for allocation in created_allocations],
            "completed_at": timezone.now().isoformat(),
        }
        metadata = dict(payment.metadata or {})
        metadata[cls.METADATA_KEY] = marker
        payment.metadata = metadata
        payment.save(update_fields=["metadata", "updated_at"])
        return PaymentProvisioningResult(
            organization=organization,
            created_license_ids=tuple(marker["license_ids"]),
            renewed_license_ids=tuple(marker["renewed_license_ids"]),
            created_allocation_ids=tuple(marker["allocation_ids"]),
        )
