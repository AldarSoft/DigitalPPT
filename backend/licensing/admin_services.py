from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.db.models import Prefetch
from django.utils import timezone

from core.models import UserNotification
from licensing.models import (
    License,
    LicenseEvent,
    LicenseOrderItemProvisioning,
    Organization,
    OrganizationMembership,
    ProductLicenseAllocation,
)
from licensing.services import (
    ClientLicenseDetailService,
    LicenseExpiryService,
    LicenseLifecycleService,
    OrganizationCoverageService,
)
from payments.models import PaymentAttempt
from products.models import Product


class AdminOrganizationLicenseService:
    ACTIVE_STATUSES = (License.Status.ACTIVE, License.Status.EXPIRING_SOON)

    @staticmethod
    def _display_name(user):
        return user.get_full_name().strip() or user.email or user.get_username()

    @classmethod
    def queryset(cls, *, search="", status="", product="", customer_id=None):
        queryset = Organization.objects.all()
        if customer_id:
            queryset = queryset.filter(
                memberships__user_id=customer_id,
                memberships__is_active=True,
            )
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
        if status == Organization.Status.DRAFT:
            queryset = queryset.filter(status=Organization.Status.DRAFT)
        elif status == License.Status.ACTIVE:
            queryset = queryset.filter(licenses__status=License.Status.ACTIVE).filter(
                models.Q(licenses__expires_on__isnull=True)
                | models.Q(
                    licenses__expires_on__gt=timezone.localdate() + timedelta(days=60)
                )
            )
        elif status == License.Status.EXPIRING_SOON:
            queryset = queryset.filter(
                models.Q(licenses__status=License.Status.EXPIRING_SOON)
                | models.Q(
                    licenses__status=License.Status.ACTIVE,
                    licenses__expires_on__range=(
                        timezone.localdate(),
                        timezone.localdate() + timedelta(days=60),
                    ),
                )
            )
        elif status == License.Status.EXPIRED:
            queryset = queryset.filter(
                models.Q(licenses__status=License.Status.EXPIRED)
                | models.Q(
                    licenses__status=License.Status.ACTIVE,
                    licenses__expires_on__lt=timezone.localdate(),
                )
            )
        elif status:
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
        needing_capacity = sum(
            1
            for organization in Organization.objects.filter(
                status=Organization.Status.ACTIVE,
                is_active=True,
            )
            .exclude(memberships__isnull=True)
            .distinct()
            if OrganizationCoverageService.summary(organization=organization)[
                "overflow_quantity"
            ]
            > 0
        )
        return {
            "organizations_with_licenses": Organization.objects.filter(
                licenses__isnull=False
            ).distinct().count(),
            "active_licenses": active_totals["total"] or 0,
            "licenses_expiring_in_60_days": expiring_totals["total"] or 0,
            "organizations_needing_capacity": needing_capacity,
            "payments_in_review": PaymentAttempt.objects.filter(
                status=PaymentAttempt.Status.PENDING
            ).count(),
        }

    @classmethod
    def status_for(cls, licenses, organization=None):
        if organization and organization.status == Organization.Status.DRAFT:
            return Organization.Status.DRAFT
        licenses = list(licenses)
        today = timezone.localdate()
        if any(
            LicenseExpiryService.effective_status(license, on_date=today)
            == License.Status.EXPIRING_SOON
            for license in licenses
        ):
            return License.Status.EXPIRING_SOON
        for status in (
            License.Status.EXPIRED,
            License.Status.ACTIVE,
            License.Status.PENDING_PAYMENT,
            License.Status.CANCELLED,
        ):
            if any(
                LicenseExpiryService.effective_status(license, on_date=today) == status
                for license in licenses
            ):
                return status
        return "no_licenses"

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
        coverage = OrganizationCoverageService.summary(organization=organization)
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
            **coverage,
            "next_expiry": next_expiry,
            "status": cls.status_for(licenses, organization),
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
            LicenseEvent.Type.CANCELLED: (
                f"{license_name} cancelled by the Organization Owner: "
                f"{metadata.get('reason', 'No reason provided.')}"
            ),
            LicenseEvent.Type.NOTIFICATION_SENT: (
                "Renewal invoice notice sent."
                if metadata.get("notification_type") == "renewal_invoice"
                else metadata.get("message", "License notification sent.")
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
            LicenseEvent.Type.OWNERSHIP_TRANSFERRED: (
                "Organization ownership transferred to "
                f"{metadata.get('new_owner_email', 'the new Owner')}."
            ),
            LicenseEvent.Type.ADJUSTED: (
                f"{license_name} cancelled by the Organization Owner: "
                f"{metadata.get('reason', 'No reason provided.')}"
                if metadata.get("action") == "owner_cancelled"
                else metadata.get("reason", "License manually adjusted.")
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
        renewal_invoice_issued = cls.event_queryset(organization).filter(
            event_type=LicenseEvent.Type.NOTIFICATION_SENT,
            metadata__notification_type="renewal_invoice",
        ).exists()
        recent_events = cls.event_queryset(organization)[:20]
        coverage = OrganizationCoverageService.summary(organization=organization)
        manual_coverage = AdminManualCoverageService.context(
            organization=organization
        )
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
                "licensed_product_count": coverage["licensed_product_count"],
                "active_quantity": coverage["licensed_product_quantity"],
                "usable_license_capacity": coverage["usable_license_capacity"],
                "overflow_quantity": coverage["overflow_quantity"],
                "status": cls.status_for(current_licenses, organization),
            },
            "licenses": [
                ClientLicenseDetailService.serialize_license(license)
                for license in licenses
            ],
            "notifications": {
                "renewal_reminder_scheduled_for": (
                    expires_on - timedelta(days=60) if expires_on else None
                ),
                "renewal_invoice_status": (
                    "issued" if renewal_invoice_issued else "not_issued"
                ),
            },
            "events": [cls.event_row(event) for event in recent_events],
            "permissions": {
                "can_adjust": True,
                "can_issue_manual_coverage": True,
                "can_send_renewal_invoice": True,
                "can_send_notification": True,
            },
            "manual_coverage": manual_coverage,
        }


    @classmethod
    def users(cls, organization):
        memberships = list(
            organization.memberships.select_related("user")
            .filter(is_active=True, user__is_active=True)
            .order_by("role", "user__first_name", "user__email", "pk")
        )

        def member_row(membership):
            return {
                "membership_id": membership.pk,
                "user_id": membership.user_id,
                "name": cls._display_name(membership.user),
                "email": membership.user.email,
                "role": membership.role,
                "status": "active",
            }

        owner = next(
            (item for item in memberships if item.role == OrganizationMembership.Role.OWNER),
            None,
        )
        invitations = organization.invitations.filter(
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at", "pk")
        return {
            "organization": {"id": organization.pk, "name": organization.name},
            "owner": member_row(owner) if owner else None,
            "license_managers": [
                member_row(item)
                for item in memberships
                if item.role == OrganizationMembership.Role.LICENSE_MANAGER
            ],
            "pending_invitations": [
                {
                    "invitation_id": invitation.pk,
                    "email": invitation.email,
                    "role": invitation.role,
                    "status": invitation.status,
                    "expires_at": invitation.expires_at,
                }
                for invitation in invitations
            ],
        }


class AdminManualCoverageService:
    """Issue audited corrective coverage without creating payment history."""

    USABLE_STATUSES = (License.Status.ACTIVE, License.Status.EXPIRING_SOON)

    @staticmethod
    def _assert_staff(actor):
        if not actor or not actor.is_authenticated or not actor.is_staff or not (
            actor.is_superuser or actor.has_perm("users.manage_licenses")
        ):
            raise PermissionDenied("Only staff can issue corrective license coverage.")

    @staticmethod
    def _represented_order_item_ids(organization):
        provisioned_ids = LicenseOrderItemProvisioning.objects.filter(
            organization=organization,
            operation=LicenseOrderItemProvisioning.Operation.PRODUCT_ALLOCATION,
        ).values_list("order_item_id", flat=True)
        legacy_ids = ProductLicenseAllocation.objects.filter(
            license__organization=organization,
            status=ProductLicenseAllocation.Status.ACTIVE,
        ).values_list("order_item_id", flat=True)
        return set(provisioned_ids).union(legacy_ids)

    @classmethod
    def context(cls, *, organization, on_date=None):
        from orders.models import OrderItem

        on_date = on_date or timezone.localdate()
        represented_ids = cls._represented_order_item_ids(organization)
        if not represented_ids:
            return {"plans": [], "candidates": []}

        order_items = list(
            OrderItem.objects.select_related(
                "order", "product__required_license_product"
            )
            .filter(
                pk__in=represented_ids,
                product__licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
                product__required_license_product__isnull=False,
            )
            .order_by("order__created_at", "pk")
        )
        purchased_by_plan = {}
        for order_item in order_items:
            plan_id = order_item.product.required_license_product_id
            purchased_by_plan[plan_id] = (
                purchased_by_plan.get(plan_id, 0) + order_item.quantity
            )

        usable_capacity_by_plan = {}
        usable_licenses = License.objects.filter(
            organization=organization,
            status__in=cls.USABLE_STATUSES,
        ).filter(models.Q(expires_on__isnull=True) | models.Q(expires_on__gte=on_date))
        for license in usable_licenses:
            usable_capacity_by_plan[license.license_product_id] = (
                usable_capacity_by_plan.get(license.license_product_id, 0)
                + license.capacity
            )
        remaining_overflow = {
            plan_id: max(0, quantity - usable_capacity_by_plan.get(plan_id, 0))
            for plan_id, quantity in purchased_by_plan.items()
        }

        active_allocations = list(
            ProductLicenseAllocation.objects.select_related("license")
            .filter(
                order_item_id__in=represented_ids,
                status=ProductLicenseAllocation.Status.ACTIVE,
            )
            .order_by("pk")
        )
        allocations_by_item = {}
        for allocation in active_allocations:
            allocations_by_item.setdefault(allocation.order_item_id, []).append(
                allocation
            )

        plans = {}
        candidates = []
        for order_item in order_items:
            plan = order_item.product.required_license_product
            if (
                plan.license_billing_model != Product.LicenseBillingModel.PER_RADIO
                or remaining_overflow.get(plan.pk, 0) <= 0
            ):
                continue
            item_allocations = allocations_by_item.get(order_item.pk, [])
            usable_allocated = sum(
                allocation.quantity
                for allocation in item_allocations
                if allocation.license.license_product_id == plan.pk
                and allocation.license.status in cls.USABLE_STATUSES
                and (
                    allocation.license.expires_on is None
                    or allocation.license.expires_on >= on_date
                )
            )
            stale_allocated = sum(
                allocation.quantity for allocation in item_allocations
            ) - usable_allocated
            uncovered = max(0, order_item.quantity - usable_allocated)
            recoverable = min(uncovered, remaining_overflow[plan.pk])
            if recoverable <= 0:
                continue
            remaining_overflow[plan.pk] -= recoverable
            plans[plan.pk] = {
                "id": plan.pk,
                "name": plan.name,
                "sku": plan.sku,
                "unit_price": plan.price,
                "term_days": plan.license_term_days,
                "available": bool(
                    plan.is_active
                    and plan.status == Product.Status.PUBLISHED
                    and plan.license_term_days
                ),
            }
            candidates.append(
                {
                    "order_item_id": order_item.pk,
                    "order_number": order_item.order.order_number,
                    "ordered_at": order_item.order.created_at,
                    "product_id": order_item.product_id,
                    "product_name": order_item.product_name,
                    "product_sku": order_item.sku,
                    "license_product_id": plan.pk,
                    "purchased_quantity": order_item.quantity,
                    "covered_quantity": usable_allocated,
                    "stale_quantity": stale_allocated,
                    "uncovered_quantity": recoverable,
                }
            )
        return {"plans": list(plans.values()), "candidates": candidates}

    @classmethod
    @transaction.atomic
    def issue(
        cls,
        *,
        organization,
        actor,
        license_product_id,
        allocations,
        reason,
        starts_on=None,
    ):
        from orders.models import OrderItem

        cls._assert_staff(actor)
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError({"reason": "A reason is required."})
        if not allocations:
            raise ValidationError({"allocations": "Select at least one radio order line."})

        locked_organization = Organization.objects.select_for_update().get(
            pk=organization.pk
        )
        try:
            plan = Product.objects.select_for_update().get(
                pk=license_product_id,
                licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
                license_billing_model=Product.LicenseBillingModel.PER_RADIO,
                status=Product.Status.PUBLISHED,
                is_active=True,
            )
        except Product.DoesNotExist as exc:
            raise ValidationError(
                {"license_product_id": "Select an active per-radio license plan."}
            ) from exc

        context = cls.context(organization=locked_organization)
        candidates = {
            row["order_item_id"]: row
            for row in context["candidates"]
            if row["license_product_id"] == plan.pk
        }
        requested = {}
        for allocation in allocations:
            order_item_id = allocation["order_item_id"]
            if order_item_id in requested:
                raise ValidationError(
                    {"allocations": "Each radio order line can only be selected once."}
                )
            requested[order_item_id] = allocation["quantity"]

        order_items = {
            item.pk: item
            for item in OrderItem.objects.select_for_update()
            .select_related("product__required_license_product", "order")
            .filter(pk__in=requested)
        }
        if len(order_items) != len(requested):
            raise ValidationError(
                {"allocations": "One or more order lines do not belong to this organization."}
            )

        total_quantity = 0
        for order_item_id, quantity in requested.items():
            candidate = candidates.get(order_item_id)
            order_item = order_items[order_item_id]
            if not candidate or order_item.product.required_license_product_id != plan.pk:
                raise ValidationError(
                    {"allocations": "An order line is not eligible for this license plan."}
                )
            if quantity <= 0 or quantity > candidate["uncovered_quantity"]:
                raise ValidationError(
                    {
                        "allocations": (
                            f"{order_item.product_name} can receive at most "
                            f"{candidate['uncovered_quantity']} corrective license(s)."
                        )
                    }
                )
            total_quantity += quantity

        starts_on = starts_on or timezone.localdate()
        license = LicenseLifecycleService.provision(
            organization=locked_organization,
            license_product=plan,
            actor=actor,
            starts_on=starts_on,
            name=f"{plan.name} - Corrective coverage",
            capacity=total_quantity,
            event_metadata={
                "manual": True,
                "action": "manual_coverage_issued",
                "reason": reason,
                "no_payment_recorded": True,
            },
        )

        released_allocation_ids = []
        created_allocation_ids = []
        for order_item_id, quantity in requested.items():
            order_item = order_items[order_item_id]
            active_allocations = list(
                ProductLicenseAllocation.objects.select_for_update()
                .select_related("license")
                .filter(
                    order_item=order_item,
                    status=ProductLicenseAllocation.Status.ACTIVE,
                )
                .order_by("pk")
            )
            free_quantity = order_item.quantity - sum(
                allocation.quantity for allocation in active_allocations
            )
            release_needed = max(0, quantity - free_quantity)
            if release_needed:
                stale_allocations = [
                    allocation
                    for allocation in active_allocations
                    if allocation.license.license_product_id != plan.pk
                    or allocation.license.status not in cls.USABLE_STATUSES
                    or (
                        allocation.license.expires_on is not None
                        and allocation.license.expires_on < timezone.localdate()
                    )
                ]
                released_quantity = 0
                for stale in stale_allocations:
                    LicenseLifecycleService.release_allocation(
                        allocation=stale,
                        actor=actor,
                        reason=(
                            f"Reassigned by corrective coverage {license.license_number}: "
                            f"{reason}"
                        ),
                    )
                    released_allocation_ids.append(stale.pk)
                    released_quantity += stale.quantity
                    if released_quantity >= release_needed:
                        break
                if released_quantity < release_needed:
                    raise ValidationError(
                        {
                            "allocations": (
                                f"{order_item.product_name} has active allocations that "
                                "cannot be safely replaced."
                            )
                        }
                    )
            created = LicenseLifecycleService.allocate(
                license=license,
                product=order_item.product,
                order_item=order_item,
                quantity=quantity,
                actor=actor,
            )
            created_allocation_ids.append(created.pk)

        LicenseLifecycleService.record_event(
            organization=locked_organization,
            license=license,
            event_type=LicenseEvent.Type.ADJUSTED,
            actor=actor,
            metadata={
                "action": "manual_coverage_issued",
                "reason": reason,
                "no_payment_recorded": True,
                "created_allocation_ids": created_allocation_ids,
                "released_allocation_ids": released_allocation_ids,
                "covered_quantity": total_quantity,
            },
        )
        return license


class AdminLicenseNotificationService:
    @classmethod
    @transaction.atomic
    def send(
        cls,
        *,
        organization,
        actor,
        title,
        message,
        license=None,
        notification_type="support",
    ):
        if not actor or not actor.is_authenticated or not actor.is_staff or not (
            actor.is_superuser or actor.has_perm("users.manage_licenses")
        ):
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
                    url=f"/account?tab=licenses&org={organization.pk}",
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
                "notification_type": notification_type,
                "recipient_ids": [recipient.pk for recipient in recipients],
            },
        )

    @classmethod
    def send_renewal_invoice(cls, *, organization, actor):
        return cls.send(
            organization=organization,
            actor=actor,
            title="Renewal review requested",
            message=(
                "Digital PTT has requested a renewal review for your organization. "
                "Open Organization licenses to review expiry dates, then contact Digital "
                "PTT support to arrange renewal. No payment has been created yet."
            ),
            notification_type="renewal_invoice",
        )
