from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from common.models import ActiveModel, TimeStampedModel


def generate_license_number():
    return f"LIC-{uuid4().hex[:12].upper()}"


class OrganizationQuerySet(models.QuerySet):
    def for_user(self, user):
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_staff:
            return self
        return self.filter(
            memberships__user=user,
            memberships__is_active=True,
        ).distinct()


class Organization(ActiveModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    billing_email = models.EmailField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_organizations",
    )

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ("name", "id")
        indexes = [
            models.Index(fields=["name", "is_active"]),
            models.Index(
                fields=["status", "is_active"],
                name="licensing_o_status_be764b_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "organization"
            candidate = base
            suffix = 2
            while Organization.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationMembership(ActiveModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Organization Owner"
        LICENSE_MANAGER = "license_manager", "License Manager"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(max_length=24, choices=Role.choices)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organization_memberships_invited",
    )

    class Meta:
        ordering = ("organization_id", "role", "user_id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "user"),
                name="licensing_unique_organization_member",
            ),
            models.UniqueConstraint(
                fields=("organization",),
                condition=Q(role="owner", is_active=True),
                name="licensing_one_active_owner_per_organization",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["organization", "role", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_role_display()} at {self.organization}"


class OrganizationInvitation(TimeStampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=24,
        choices=OrganizationMembership.Role.choices,
        default=OrganizationMembership.Role.LICENSE_MANAGER,
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organization_invitations_sent",
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organization_invitations_accepted",
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(accepted_at__isnull=True) | Q(revoked_at__isnull=True),
                name="licensing_invitation_not_accepted_and_revoked",
            ),
            models.CheckConstraint(
                condition=Q(accepted_at__isnull=False) | Q(accepted_by__isnull=True),
                name="licensing_invitation_acceptor_requires_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "email"]),
            models.Index(fields=["expires_at", "accepted_at", "revoked_at"]),
        ]

    @property
    def status(self):
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= timezone.now():
            return "expired"
        return "pending"

    def clean(self):
        super().clean()
        self.email = self.email.strip().casefold()
        if self.accepted_at and self.revoked_at:
            raise ValidationError("An invitation cannot be both accepted and revoked.")
        if self.accepted_by_id and not self.accepted_at:
            raise ValidationError({"accepted_by": "Accepted invitations require accepted_at."})

    def __str__(self):
        return f"{self.email} invited to {self.organization} ({self.status})"


class OrganizationScopedQuerySet(models.QuerySet):
    organization_path = "organization"

    def for_user(self, user):
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_staff:
            return self
        filters = {
            f"{self.organization_path}__memberships__user": user,
            f"{self.organization_path}__memberships__is_active": True,
        }
        return self.filter(**filters).distinct()


class LicenseQuerySet(OrganizationScopedQuerySet):
    pass


class License(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        ACTIVE = "active", "Active"
        EXPIRING_SOON = "expiring_soon", "Expiring soon"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="licenses",
    )
    license_product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="issued_licenses",
    )
    license_number = models.CharField(
        max_length=40,
        unique=True,
        default=generate_license_number,
        editable=False,
    )
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
    )
    capacity = models.PositiveIntegerField()
    used_capacity = models.PositiveIntegerField(default=0)
    starts_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True, db_index=True)
    renews_on = models.DateField(null=True, blank=True)
    source_order_item = models.ForeignKey(
        "orders.OrderItem",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_licenses",
    )

    objects = LicenseQuerySet.as_manager()

    class Meta:
        ordering = ("expires_on", "created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(capacity__gt=0),
                name="licensing_license_capacity_positive",
            ),
            models.CheckConstraint(
                condition=Q(used_capacity__gte=0) & Q(used_capacity__lte=models.F("capacity")),
                name="licensing_license_used_within_capacity",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "license_product", "status"]),
        ]

    @property
    def available_capacity(self):
        return self.capacity - self.used_capacity

    def calculate_remaining_days(self, on_date=None):
        if not self.expires_on:
            return None
        on_date = on_date or timezone.localdate()
        return (self.expires_on - on_date).days

    @property
    def remaining_days(self):
        return self.calculate_remaining_days()

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.license_product_id
            and self.license_product.licensing_role
            != self.license_product.LicensingRole.LICENSE_PRODUCT
        ):
            errors["license_product"] = "Licenses must reference a license product."
        if self.used_capacity > self.capacity:
            errors["used_capacity"] = "Used capacity cannot exceed license capacity."
        if self.source_order_item_id and self.source_order_item.product_id:
            if self.source_order_item.product_id != self.license_product_id:
                errors["source_order_item"] = (
                    "The source order item must contain this license product."
                )
        if self.starts_on and self.expires_on and self.expires_on < self.starts_on:
            errors["expires_on"] = "Expiry cannot be before the license start date."
        if self.expires_on and self.renews_on and self.renews_on <= self.expires_on:
            errors["renews_on"] = "Renewal must be after the expiry date."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.license_number} - {self.organization}"


class ProductLicenseAllocationQuerySet(OrganizationScopedQuerySet):
    organization_path = "license__organization"

    def delete(self):
        raise ValidationError("Allocations must be released, not deleted.")


class ProductLicenseAllocation(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"

    license = models.ForeignKey(
        License,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="license_allocations",
    )
    order_item = models.ForeignKey(
        "orders.OrderItem",
        on_delete=models.PROTECT,
        related_name="license_allocations",
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    released_at = models.DateTimeField(null=True, blank=True)

    objects = ProductLicenseAllocationQuerySet.as_manager()

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="licensing_allocation_quantity_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="active", released_at__isnull=True)
                    | Q(status="released", released_at__isnull=False)
                ),
                name="licensing_allocation_release_state_valid",
            ),
            models.UniqueConstraint(
                fields=("license", "order_item"),
                condition=Q(status="active"),
                name="licensing_one_active_allocation_per_license_order_item",
            ),
        ]
        indexes = [
            models.Index(fields=["license", "status"]),
            models.Index(fields=["order_item", "status"]),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.product_id and self.product.licensing_role != self.product.LicensingRole.LICENSED_PRODUCT:
            errors["product"] = "Only licensed products can consume license capacity."
        if (
            self.product_id
            and self.license_id
            and self.product.required_license_product_id != self.license.license_product_id
        ):
            errors["license"] = "This license is not compatible with the product."
        if self.order_item_id and self.order_item.product_id != self.product_id:
            errors["order_item"] = "The order item must contain the allocated product."
        if self.status == self.Status.ACTIVE and self.released_at:
            errors["released_at"] = "Active allocations cannot have a release time."
        if self.status == self.Status.RELEASED and not self.released_at:
            errors["released_at"] = "Released allocations require a release time."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Allocations are immutable; release them through the service.")
        self.full_clean()
        with transaction.atomic():
            locked_license = License.objects.select_for_update().get(pk=self.license_id)
            if self.quantity > locked_license.available_capacity:
                raise ValidationError(
                    {"quantity": "This allocation exceeds the license's available capacity."}
                )
            self.license = locked_license
            result = super().save(*args, **kwargs)
            locked_license.used_capacity += self.quantity
            locked_license.save(update_fields=["used_capacity", "updated_at"])
        return result

    def delete(self, *args, **kwargs):
        raise ValidationError("Allocations must be released, not deleted.")

    def __str__(self):
        return f"{self.quantity} x {self.product} on {self.license.license_number}"


class LicenseOrderItemProvisioningQuerySet(OrganizationScopedQuerySet):
    def delete(self):
        raise ValidationError("Provisioning records are immutable and cannot be deleted.")


class LicenseOrderItemProvisioning(TimeStampedModel):
    class Operation(models.TextChoices):
        LICENSE_PURCHASE = "license_purchase", "License purchase"
        PRODUCT_ALLOCATION = "product_allocation", "Product allocation"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="order_item_provisioning_records",
    )
    order_item = models.OneToOneField(
        "orders.OrderItem",
        on_delete=models.PROTECT,
        related_name="license_provisioning_record",
    )
    operation = models.CharField(max_length=24, choices=Operation.choices)
    created_license_ids = models.JSONField(default=list, blank=True)
    renewed_license_ids = models.JSONField(default=list, blank=True)
    allocation_ids = models.JSONField(default=list, blank=True)
    completed_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = LicenseOrderItemProvisioningQuerySet.as_manager()

    class Meta:
        ordering = ("completed_at", "id")
        indexes = [
            models.Index(fields=["organization", "operation", "completed_at"]),
        ]

    def clean(self):
        super().clean()
        if not self.order_item_id or not self.order_item.product_id:
            return
        role = self.order_item.product.licensing_role
        expected_operation = (
            self.Operation.LICENSE_PURCHASE
            if role == self.order_item.product.LicensingRole.LICENSE_PRODUCT
            else self.Operation.PRODUCT_ALLOCATION
        )
        if role == self.order_item.product.LicensingRole.STANDARD:
            raise ValidationError(
                {"order_item": "Standard products do not have license provisioning records."}
            )
        if self.operation != expected_operation:
            raise ValidationError(
                {"operation": "The operation does not match the order-item product role."}
            )

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Provisioning records are immutable and cannot be changed.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Provisioning records are immutable and cannot be deleted.")

    def __str__(self):
        return f"{self.order_item} - {self.get_operation_display()}"


class LicenseEventQuerySet(OrganizationScopedQuerySet):
    def delete(self):
        raise ValidationError("License events are immutable and cannot be deleted.")


class LicenseEvent(TimeStampedModel):
    class Type(models.TextChoices):
        PROVISIONED = "provisioned", "License provisioned"
        RENEWED = "renewed", "License renewed"
        EXPIRED = "expired", "License expired"
        NOTIFICATION_SENT = "notification_sent", "Notification sent"
        INVITATION_SENT = "invitation_sent", "Invitation sent"
        INVITATION_ACCEPTED = "invitation_accepted", "Invitation accepted"
        INVITATION_REVOKED = "invitation_revoked", "Invitation revoked"
        OWNERSHIP_TRANSFERRED = "ownership_transferred", "Organization ownership transferred"
        ADJUSTED = "adjusted", "Manual adjustment"
        ALLOCATED = "allocated", "Product capacity allocated"
        ALLOCATION_RELEASED = "allocation_released", "Product allocation released"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="license_events",
    )
    license = models.ForeignKey(
        License,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    invitation = models.ForeignKey(
        OrganizationInvitation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="license_events",
    )
    event_type = models.CharField(max_length=32, choices=Type.choices, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="license_events_performed",
    )
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = LicenseEventQuerySet.as_manager()

    class Meta:
        ordering = ("-occurred_at", "-id")
        indexes = [
            models.Index(fields=["organization", "event_type", "occurred_at"]),
            models.Index(fields=["license", "occurred_at"]),
        ]

    def clean(self):
        super().clean()
        if self.license_id and self.license.organization_id != self.organization_id:
            raise ValidationError({"license": "The license belongs to another organization."})
        if self.invitation_id and self.invitation.organization_id != self.organization_id:
            raise ValidationError(
                {"invitation": "The invitation belongs to another organization."}
            )

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("License events are immutable and cannot be changed.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("License events are immutable and cannot be deleted.")

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.organization}"
