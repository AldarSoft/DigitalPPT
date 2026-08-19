from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import UserNotification
from licensing.models import Organization, OrganizationInvitation, OrganizationMembership
from licensing.permissions import OrganizationAccessPolicy
from licensing.models import License, LicenseEvent, ProductLicenseAllocation
from licensing.services import (
    InvitationService,
    LicenseCapacityService,
    LicenseExpiryService,
    LicenseLifecycleService,
    OrganizationService,
    ProductLicenseCompatibilityService,
)
from orders.models import Order, OrderItem
from products.models import Category, Product


class OrganizationDomainTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="StrongPass123!",
        )
        self.manager = User.objects.create_user(
            username="manager@example.com",
            email="manager@example.com",
            password="StrongPass123!",
        )
        self.outsider = User.objects.create_user(
            username="outsider@example.com",
            email="outsider@example.com",
            password="StrongPass123!",
        )
        self.staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.organization = OrganizationService.create(
            name="Digital PTT Aldarsoft",
            owner=self.owner,
            billing_email="BILLING@EXAMPLE.COM",
        )

    def test_create_organization_assigns_stable_reference_and_owner(self):
        membership = self.organization.memberships.get()

        self.assertIsNotNone(self.organization.public_id)
        self.assertEqual(self.organization.slug, "digital-ptt-aldarsoft")
        self.assertEqual(self.organization.billing_email, "billing@example.com")
        self.assertEqual(membership.user, self.owner)
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)

    def test_create_organization_requires_a_name(self):
        with self.assertRaises(ValidationError):
            OrganizationService.create(name="  ", owner=self.owner)

    def test_organization_slug_remains_stable_when_name_changes(self):
        original_slug = self.organization.slug
        self.organization.name = "Renamed Organization"
        self.organization.save()

        self.assertEqual(self.organization.slug, original_slug)

    def test_database_allows_only_one_active_owner(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=self.outsider,
                role=OrganizationMembership.Role.OWNER,
            )

    def test_access_policy_separates_license_and_team_permissions(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=OrganizationMembership.Role.LICENSE_MANAGER,
        )

        self.assertTrue(
            OrganizationAccessPolicy.can_manage_licenses(
                user=self.manager,
                organization=self.organization,
            )
        )
        self.assertFalse(
            OrganizationAccessPolicy.can_manage_team(
                user=self.manager,
                organization=self.organization,
            )
        )
        self.assertTrue(
            OrganizationAccessPolicy.can_manage_team(
                user=self.owner,
                organization=self.organization,
            )
        )
        self.assertTrue(
            OrganizationAccessPolicy.can_manage_team(
                user=self.staff,
                organization=self.organization,
            )
        )
        self.assertFalse(
            OrganizationAccessPolicy.can_view(
                user=self.outsider,
                organization=self.organization,
            )
        )

    def test_organization_queryset_returns_only_accessible_records(self):
        other = OrganizationService.create(name="Other", owner=self.outsider)

        self.assertQuerySetEqual(
            Organization.objects.for_user(self.owner),
            [self.organization],
        )
        self.assertQuerySetEqual(
            Organization.objects.for_user(self.staff),
            [self.organization, other],
            ordered=False,
        )


class OrganizationInvitationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="StrongPass123!",
        )
        self.manager = User.objects.create_user(
            username="manager@example.com",
            email="manager@example.com",
            password="StrongPass123!",
        )
        self.other = User.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="StrongPass123!",
        )
        self.organization = OrganizationService.create(
            name="Invitation Organization",
            owner=self.owner,
        )

    def issue(self, **kwargs):
        return InvitationService.issue(
            organization=self.organization,
            email=self.manager.email,
            invited_by=self.owner,
            **kwargs,
        )

    def test_issue_stores_only_a_hash_and_normalizes_email(self):
        invitation, token = InvitationService.issue(
            organization=self.organization,
            email="  MANAGER@EXAMPLE.COM ",
            invited_by=self.owner,
        )

        self.assertEqual(invitation.email, "manager@example.com")
        self.assertNotEqual(invitation.token_hash, token)
        self.assertEqual(invitation.token_hash, InvitationService.hash_token(token))
        self.assertEqual(invitation.status, "pending")

    def test_issue_rejects_an_invalid_email(self):
        with self.assertRaises(ValidationError):
            InvitationService.issue(
                organization=self.organization,
                email="not-an-email",
                invited_by=self.owner,
            )

    def test_reissuing_revokes_previous_pending_invitation(self):
        previous, previous_token = self.issue()
        replacement, replacement_token = self.issue()
        previous.refresh_from_db()

        self.assertEqual(previous.status, "revoked")
        self.assertEqual(replacement.status, "pending")
        self.assertNotEqual(previous_token, replacement_token)

    def test_accept_creates_license_manager_membership_and_is_idempotent(self):
        invitation, token = self.issue()

        membership = InvitationService.accept(token=token, user=self.manager)
        repeated = InvitationService.accept(token=token, user=self.manager)
        invitation.refresh_from_db()

        self.assertEqual(membership, repeated)
        self.assertEqual(membership.role, OrganizationMembership.Role.LICENSE_MANAGER)
        self.assertEqual(invitation.accepted_by, self.manager)
        self.assertEqual(invitation.status, "accepted")
        self.assertEqual(
            OrganizationMembership.objects.filter(
                organization=self.organization,
                user=self.manager,
            ).count(),
            1,
        )

    def test_wrong_email_cannot_accept_invitation(self):
        _, token = self.issue()

        with self.assertRaises(PermissionDenied):
            InvitationService.accept(token=token, user=self.other)

    def test_expired_invitation_cannot_be_accepted(self):
        invitation, token = self.issue(expires_in=timedelta(seconds=-1))

        self.assertEqual(invitation.status, "expired")
        with self.assertRaises(ValidationError):
            InvitationService.accept(token=token, user=self.manager)

    def test_owner_can_revoke_and_revoked_invitation_cannot_be_accepted(self):
        invitation, token = self.issue()

        InvitationService.revoke(invitation=invitation, revoked_by=self.owner)
        invitation.refresh_from_db()

        self.assertEqual(invitation.status, "revoked")
        with self.assertRaises(ValidationError):
            InvitationService.accept(token=token, user=self.manager)

    def test_license_manager_cannot_invite_or_revoke(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=OrganizationMembership.Role.LICENSE_MANAGER,
        )
        invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email=self.other.email,
            token_hash="a" * 64,
            expires_at=timezone.now() + timedelta(days=7),
            invited_by=self.owner,
        )

        with self.assertRaises(PermissionDenied):
            InvitationService.issue(
                organization=self.organization,
                email=self.other.email,
                invited_by=self.manager,
            )
        with self.assertRaises(PermissionDenied):
            InvitationService.revoke(invitation=invitation, revoked_by=self.manager)


class LicenseLifecycleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="license-owner@example.com",
            email="license-owner@example.com",
            password="StrongPass123!",
        )
        self.manager = User.objects.create_user(
            username="license-manager@example.com",
            email="license-manager@example.com",
            password="StrongPass123!",
        )
        self.outsider = User.objects.create_user(
            username="license-outsider@example.com",
            email="license-outsider@example.com",
            password="StrongPass123!",
        )
        self.staff = User.objects.create_user(
            username="license-staff@example.com",
            email="license-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.organization = OrganizationService.create(
            name="Lifecycle Organization",
            owner=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=OrganizationMembership.Role.LICENSE_MANAGER,
        )
        license_category = Category.objects.create(name="Lifecycle Licenses")
        radio_category = Category.objects.create(name="Lifecycle Radios")
        self.license_product = Product.objects.create(
            category=license_category,
            name="Lifecycle Business License",
            sku="LIFECYCLE-LIC-3",
            price="100.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=3,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )
        self.other_license_product = Product.objects.create(
            category=license_category,
            name="Other License",
            sku="OTHER-LIC-3",
            price="100.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=3,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )
        self.radio = Product.objects.create(
            category=radio_category,
            name="Lifecycle Radio",
            sku="LIFECYCLE-RADIO",
            price="250.00",
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.license_product,
            status=Product.Status.PUBLISHED,
        )
        self.order = Order.objects.create(
            user=self.owner,
            customer_first_name="License",
            customer_last_name="Owner",
            customer_email=self.owner.email,
            shipping_address="1 Main Street",
            shipping_city="Ulaanbaatar",
            shipping_country="Mongolia",
            subtotal="850.00",
            total="850.00",
        )
        self.license_order_item = OrderItem.objects.create(
            order=self.order,
            product=self.license_product,
            product_name=self.license_product.name,
            sku=self.license_product.sku,
            unit_price="100.00",
            quantity=1,
            line_total="100.00",
        )
        self.radio_order_item = OrderItem.objects.create(
            order=self.order,
            product=self.radio,
            product_name=self.radio.name,
            sku=self.radio.sku,
            unit_price="250.00",
            quantity=3,
            line_total="750.00",
        )

    def provision(self, **kwargs):
        return LicenseLifecycleService.provision(
            organization=self.organization,
            license_product=self.license_product,
            source_order_item=self.license_order_item,
            actor=self.staff,
            **kwargs,
        )

    def test_provision_creates_dates_capacity_source_and_immutable_event(self):
        starts_on = timezone.localdate()
        license = self.provision(starts_on=starts_on, name="RadioAdmin License 01")

        self.assertTrue(license.license_number.startswith("LIC-"))
        self.assertEqual(license.capacity, 3)
        self.assertEqual(license.used_capacity, 0)
        self.assertEqual(license.available_capacity, 3)
        self.assertEqual(license.starts_on, starts_on)
        self.assertEqual(license.expires_on, starts_on + timedelta(days=364))
        self.assertEqual(license.renews_on, starts_on + timedelta(days=365))
        self.assertEqual(license.source_order_item, self.license_order_item)
        event = license.events.get(event_type=LicenseEvent.Type.PROVISIONED)
        self.assertEqual(event.organization, self.organization)
        self.assertEqual(event.metadata["capacity"], 3)

    def test_provision_rejects_standard_product_and_wrong_source_item(self):
        with self.assertRaises(ValidationError):
            LicenseLifecycleService.provision(
                organization=self.organization,
                license_product=self.radio,
            )
        with self.assertRaises(ValidationError):
            LicenseLifecycleService.provision(
                organization=self.organization,
                license_product=self.license_product,
                source_order_item=self.radio_order_item,
            )

    def test_allocation_updates_capacity_and_records_event(self):
        license = self.provision()

        allocation = LicenseLifecycleService.allocate(
            license=license,
            product=self.radio,
            order_item=self.radio_order_item,
            quantity=2,
            actor=self.owner,
        )
        license.refresh_from_db()

        self.assertEqual(allocation.status, ProductLicenseAllocation.Status.ACTIVE)
        self.assertEqual(license.used_capacity, 2)
        self.assertEqual(license.available_capacity, 1)
        self.assertTrue(
            license.events.filter(event_type=LicenseEvent.Type.ALLOCATED).exists()
        )

    def test_allocation_cannot_exceed_license_capacity(self):
        license = self.provision()
        OrderItem.objects.filter(pk=self.radio_order_item.pk).update(quantity=4)
        self.radio_order_item.refresh_from_db()

        with self.assertRaises(ValidationError):
            LicenseLifecycleService.allocate(
                license=license,
                product=self.radio,
                order_item=self.radio_order_item,
                quantity=4,
            )

        license.refresh_from_db()
        self.assertEqual(license.used_capacity, 0)
        self.assertFalse(ProductLicenseAllocation.objects.exists())

    def test_allocations_cannot_exceed_source_order_quantity_across_licenses(self):
        first_license = self.provision(name="License 1")
        second_license = self.provision(name="License 2")
        LicenseLifecycleService.allocate(
            license=first_license,
            product=self.radio,
            order_item=self.radio_order_item,
            quantity=2,
        )

        with self.assertRaises(ValidationError):
            LicenseLifecycleService.allocate(
                license=second_license,
                product=self.radio,
                order_item=self.radio_order_item,
                quantity=2,
            )

    def test_allocation_rejects_incompatible_license(self):
        other_license = LicenseLifecycleService.provision(
            organization=self.organization,
            license_product=self.other_license_product,
        )

        with self.assertRaises(ValidationError):
            LicenseLifecycleService.allocate(
                license=other_license,
                product=self.radio,
                order_item=self.radio_order_item,
                quantity=1,
            )

    def test_release_restores_capacity_and_allocation_cannot_be_edited_or_deleted(self):
        license = self.provision()
        allocation = LicenseLifecycleService.allocate(
            license=license,
            product=self.radio,
            order_item=self.radio_order_item,
            quantity=2,
        )

        released = LicenseLifecycleService.release_allocation(
            allocation=allocation,
            actor=self.staff,
            reason="Order corrected",
        )
        license.refresh_from_db()

        self.assertEqual(released.status, ProductLicenseAllocation.Status.RELEASED)
        self.assertIsNotNone(released.released_at)
        self.assertEqual(license.used_capacity, 0)
        with self.assertRaises(ValidationError):
            released.save()
        with self.assertRaises(ValidationError):
            released.delete()

    def test_renewal_preserves_remaining_term_and_records_event(self):
        license = self.provision(starts_on=timezone.localdate())
        previous_expiry = license.expires_on

        renewed = LicenseLifecycleService.renew(license=license, actor=self.staff)

        self.assertEqual(renewed.expires_on, previous_expiry + timedelta(days=365))
        self.assertEqual(renewed.renews_on, renewed.expires_on + timedelta(days=1))
        self.assertTrue(
            renewed.events.filter(event_type=LicenseEvent.Type.RENEWED).exists()
        )

    def test_database_rejects_used_capacity_above_capacity(self):
        license = self.provision()

        with self.assertRaises(IntegrityError), transaction.atomic():
            License.objects.filter(pk=license.pk).update(used_capacity=4)

    def test_events_are_append_only(self):
        license = self.provision()
        event = license.events.get(event_type=LicenseEvent.Type.PROVISIONED)
        event.metadata = {"changed": True}

        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            LicenseEvent.objects.filter(pk=event.pk).delete()

    def test_lifecycle_querysets_are_isolated_by_organization(self):
        license = self.provision()
        allocation = LicenseLifecycleService.allocate(
            license=license,
            product=self.radio,
            order_item=self.radio_order_item,
            quantity=1,
        )
        other_organization = OrganizationService.create(
            name="Other Lifecycle Organization",
            owner=self.outsider,
        )
        other_license = LicenseLifecycleService.provision(
            organization=other_organization,
            license_product=self.license_product,
        )

        self.assertQuerySetEqual(License.objects.for_user(self.owner), [license])
        self.assertQuerySetEqual(License.objects.for_user(self.manager), [license])
        self.assertQuerySetEqual(License.objects.for_user(self.outsider), [other_license])
        self.assertEqual(License.objects.for_user(self.staff).count(), 2)
        self.assertEqual(
            ProductLicenseAllocation.objects.for_user(self.owner).get(),
            allocation,
        )
        self.assertFalse(
            ProductLicenseAllocation.objects.for_user(self.outsider).exists()
        )
        self.assertTrue(LicenseEvent.objects.for_user(self.owner).exists())
        self.assertFalse(
            LicenseEvent.objects.for_user(self.outsider).filter(license=license).exists()
        )
        self.assertTrue(
            LicenseEvent.objects.for_user(self.outsider)
            .filter(license=other_license)
            .exists()
        )

    def test_expiry_reconciliation_calculates_days_and_notifies_once_per_stage(self):
        license = self.provision()
        expiry = timezone.localdate() + timedelta(days=30)
        License.objects.filter(pk=license.pk).update(
            expires_on=expiry,
            renews_on=expiry + timedelta(days=1),
        )
        license.refresh_from_db()

        reconciled, first_notified = LicenseExpiryService.reconcile(license=license)
        _, repeated_notified = LicenseExpiryService.reconcile(license=license)

        self.assertEqual(reconciled.remaining_days, 30)
        self.assertEqual(reconciled.status, License.Status.EXPIRING_SOON)
        self.assertTrue(first_notified)
        self.assertFalse(repeated_notified)
        self.assertEqual(UserNotification.objects.count(), 3)
        self.assertSetEqual(
            set(UserNotification.objects.values_list("recipient_id", flat=True)),
            {self.owner.pk, self.manager.pk, self.staff.pk},
        )
        self.assertEqual(
            LicenseEvent.objects.filter(
                license=license,
                event_type=LicenseEvent.Type.NOTIFICATION_SENT,
            ).count(),
            1,
        )

    def test_expired_license_notifies_without_disabling_allocated_products(self):
        license = self.provision()
        License.objects.filter(pk=license.pk).update(
            used_capacity=2,
            expires_on=timezone.localdate() - timedelta(days=1),
            renews_on=timezone.localdate(),
        )
        license.refresh_from_db()

        reconciled, notified = LicenseExpiryService.reconcile(license=license)

        self.assertTrue(notified)
        self.assertEqual(reconciled.remaining_days, -1)
        self.assertEqual(reconciled.status, License.Status.EXPIRED)
        self.assertEqual(reconciled.used_capacity, 2)
        self.assertEqual(
            LicenseEvent.objects.filter(
                license=license,
                event_type=LicenseEvent.Type.EXPIRED,
            ).count(),
            1,
        )

    def test_only_staff_can_make_audited_capacity_and_status_adjustments(self):
        license = self.provision()
        url = f"/api/v1/licensing/licenses/{license.pk}/adjust/"
        payload = {
            "capacity": 5,
            "status": License.Status.EXPIRING_SOON,
            "reason": "Approved support correction",
        }
        api_client = APIClient()
        api_client.force_authenticate(user=self.manager)
        forbidden = api_client.post(url, payload)

        api_client.force_authenticate(user=self.staff)
        response = api_client.post(url, payload)

        license.refresh_from_db()
        event = LicenseEvent.objects.get(
            license=license,
            event_type=LicenseEvent.Type.ADJUSTED,
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["remaining_days"], license.remaining_days)
        self.assertEqual(license.capacity, 5)
        self.assertEqual(license.status, License.Status.EXPIRING_SOON)
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.metadata["reason"], payload["reason"])
        self.assertEqual(event.metadata["previous"]["capacity"], 3)
        self.assertEqual(event.metadata["current"]["capacity"], 5)

    def test_manual_capacity_cannot_drop_below_allocated_quantity(self):
        license = self.provision()
        LicenseLifecycleService.allocate(
            license=license,
            product=self.radio,
            order_item=self.radio_order_item,
            quantity=2,
        )
        api_client = APIClient()
        api_client.force_authenticate(user=self.staff)

        response = api_client.post(
            f"/api/v1/licensing/licenses/{license.pk}/adjust/",
            {"capacity": 1, "reason": "Invalid correction"},
        )

        license.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(license.capacity, 3)
        self.assertFalse(
            LicenseEvent.objects.filter(
                license=license,
                event_type=LicenseEvent.Type.ADJUSTED,
            ).exists()
        )

    def test_client_organization_summary_aggregates_licenses_and_team(self):
        today = timezone.localdate()
        active_license = self.provision(name="Active License")
        expired_license = self.provision(name="Expired License")
        License.objects.filter(pk=active_license.pk).update(
            status=License.Status.EXPIRING_SOON,
            used_capacity=2,
            expires_on=today + timedelta(days=30),
            renews_on=today + timedelta(days=31),
        )
        License.objects.filter(pk=expired_license.pk).update(
            status=License.Status.EXPIRED,
            used_capacity=1,
            expires_on=today - timedelta(days=1),
            renews_on=today,
        )
        InvitationService.issue(
            organization=self.organization,
            email="pending-manager@example.com",
            invited_by=self.owner,
        )
        api_client = APIClient()
        api_client.force_authenticate(user=self.owner)

        response = api_client.get("/api/v1/licensing/organization/summary/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organization"]["id"], self.organization.pk)
        self.assertEqual(response.data["organization"]["current_user_role"], "owner")
        self.assertEqual(response.data["summary"]["license_count"], 2)
        self.assertEqual(response.data["summary"]["active_license_count"], 1)
        self.assertEqual(response.data["summary"]["expiring_soon_count"], 1)
        self.assertEqual(response.data["summary"]["expired_license_count"], 1)
        self.assertEqual(response.data["summary"]["total_capacity"], 6)
        self.assertEqual(response.data["summary"]["used_capacity"], 3)
        self.assertEqual(response.data["summary"]["available_capacity"], 3)
        self.assertEqual(
            response.data["summary"]["next_expiry"],
            (today + timedelta(days=30)).isoformat(),
        )
        self.assertEqual(response.data["summary"]["next_expiry_remaining_days"], 30)
        self.assertEqual(response.data["team"]["owner"]["email"], self.owner.email)
        self.assertEqual(response.data["team"]["license_manager_count"], 1)
        self.assertEqual(response.data["team"]["pending_invitation_count"], 1)

    def test_license_manager_summary_reports_manager_role(self):
        self.provision()
        api_client = APIClient()
        api_client.force_authenticate(user=self.manager)

        response = api_client.get("/api/v1/licensing/organization/summary/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organization"]["id"], self.organization.pk)
        self.assertEqual(
            response.data["organization"]["current_user_role"],
            "license_manager",
        )

    def test_organization_summary_is_scoped_and_requires_membership(self):
        other_organization = OrganizationService.create(
            name="Other Summary Organization",
            owner=self.outsider,
        )
        LicenseLifecycleService.provision(
            organization=other_organization,
            license_product=self.license_product,
        )
        User = get_user_model()
        no_organization_user = User.objects.create_user(
            username="no-organization@example.com",
            email="no-organization@example.com",
            password="StrongPass123!",
        )
        api_client = APIClient()

        anonymous = api_client.get("/api/v1/licensing/organization/summary/")
        api_client.force_authenticate(user=no_organization_user)
        missing = api_client.get("/api/v1/licensing/organization/summary/")
        api_client.force_authenticate(user=self.outsider)
        scoped = api_client.get("/api/v1/licensing/organization/summary/")

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(scoped.status_code, 200)
        self.assertEqual(scoped.data["organization"]["id"], other_organization.pk)
        self.assertEqual(scoped.data["summary"]["license_count"], 1)

    def test_client_license_list_returns_capacity_expiry_and_status(self):
        today = timezone.localdate()
        active_license = self.provision(name="Client Active License")
        expired_license = self.provision(name="Client Expired License")
        cancelled_license = self.provision(name="Client Cancelled License")
        License.objects.filter(pk=active_license.pk).update(
            status=License.Status.EXPIRING_SOON,
            used_capacity=2,
            expires_on=today + timedelta(days=30),
            renews_on=today + timedelta(days=31),
        )
        License.objects.filter(pk=expired_license.pk).update(
            status=License.Status.EXPIRED,
            used_capacity=1,
            expires_on=today - timedelta(days=1),
            renews_on=today,
        )
        License.objects.filter(pk=cancelled_license.pk).update(
            status=License.Status.CANCELLED,
        )
        api_client = APIClient()
        api_client.force_authenticate(user=self.owner)

        response = api_client.get("/api/v1/licensing/organization/licenses/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organization"]["id"], self.organization.pk)
        self.assertEqual(response.data["organization"]["role"], "owner")
        self.assertEqual(response.data["summary"]["license_count"], 2)
        by_number = {
            item["license_number"]: item for item in response.data["licenses"]
        }
        self.assertSetEqual(
            set(by_number),
            {active_license.license_number, expired_license.license_number},
        )
        active_payload = by_number[active_license.license_number]
        self.assertEqual(active_payload["plan_name"], self.license_product.name)
        self.assertEqual(active_payload["plan_sku"], self.license_product.sku)
        self.assertEqual(active_payload["status"], License.Status.EXPIRING_SOON)
        self.assertEqual(active_payload["capacity"], 3)
        self.assertEqual(active_payload["used_capacity"], 2)
        self.assertEqual(active_payload["available_capacity"], 1)
        self.assertEqual(active_payload["capacity_percentage"], 67)
        self.assertEqual(active_payload["remaining_days"], 30)
        self.assertEqual(
            active_payload["expires_on"],
            (today + timedelta(days=30)).isoformat(),
        )
        self.assertEqual(
            by_number[expired_license.license_number]["remaining_days"],
            -1,
        )

    def test_client_license_list_is_membership_scoped(self):
        self.provision()
        other_organization = OrganizationService.create(
            name="Other License List Organization",
            owner=self.outsider,
        )
        other_license = LicenseLifecycleService.provision(
            organization=other_organization,
            license_product=self.license_product,
        )
        User = get_user_model()
        no_organization_user = User.objects.create_user(
            username="no-license-list-organization@example.com",
            email="no-license-list-organization@example.com",
            password="StrongPass123!",
        )
        api_client = APIClient()

        anonymous = api_client.get("/api/v1/licensing/organization/licenses/")
        api_client.force_authenticate(user=no_organization_user)
        missing = api_client.get("/api/v1/licensing/organization/licenses/")
        api_client.force_authenticate(user=self.outsider)
        scoped = api_client.get("/api/v1/licensing/organization/licenses/")

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(scoped.status_code, 200)
        self.assertEqual(scoped.data["organization"]["id"], other_organization.pk)
        self.assertEqual(len(scoped.data["licenses"]), 1)
        self.assertEqual(
            scoped.data["licenses"][0]["license_number"],
            other_license.license_number,
        )

    def test_client_license_detail_returns_subscription_and_source_allocations(self):
        license = self.provision(name="RadioAdmin License 01")
        allocation = LicenseLifecycleService.allocate(
            license=license,
            product=self.radio,
            order_item=self.radio_order_item,
            quantity=2,
        )
        api_client = APIClient()
        api_client.force_authenticate(user=self.owner)

        response = api_client.get(
            f"/api/v1/licensing/licenses/{license.license_number}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["license_number"], license.license_number)
        self.assertEqual(response.data["plan_name"], self.license_product.name)
        self.assertEqual(response.data["used_capacity"], 2)
        self.assertEqual(response.data["available_capacity"], 1)
        self.assertEqual(
            response.data["subscription"]["term_days"],
            self.license_product.license_term_days,
        )
        self.assertEqual(
            response.data["subscription"]["source_order"]["order_number"],
            self.order.order_number,
        )
        self.assertEqual(len(response.data["allocations"]), 1)
        allocation_payload = response.data["allocations"][0]
        self.assertEqual(allocation_payload["id"], allocation.pk)
        self.assertEqual(allocation_payload["product"]["id"], self.radio.pk)
        self.assertEqual(allocation_payload["quantity"], 2)
        self.assertEqual(
            allocation_payload["source_order"]["order_number"],
            self.order.order_number,
        )

    def test_client_license_detail_is_organization_scoped(self):
        license = self.provision()
        other_organization = OrganizationService.create(
            name="Other Detail Organization",
            owner=self.outsider,
        )
        other_license = LicenseLifecycleService.provision(
            organization=other_organization,
            license_product=self.license_product,
        )
        api_client = APIClient()

        anonymous = api_client.get(
            f"/api/v1/licensing/licenses/{license.license_number}/"
        )
        api_client.force_authenticate(user=self.manager)
        manager = api_client.get(
            f"/api/v1/licensing/licenses/{license.license_number}/"
        )
        api_client.force_authenticate(user=self.outsider)
        hidden = api_client.get(
            f"/api/v1/licensing/licenses/{license.license_number}/"
        )
        own = api_client.get(
            f"/api/v1/licensing/licenses/{other_license.license_number}/"
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(manager.status_code, 200)
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(own.status_code, 200)

    def test_client_team_lists_members_and_pending_invitations(self):
        invitation, _token = InvitationService.issue(
            organization=self.organization,
            email="Pending.Manager@Example.com",
            invited_by=self.owner,
        )
        api_client = APIClient()
        api_client.force_authenticate(user=self.owner)

        owner_response = api_client.get("/api/v1/licensing/organization/team/")
        api_client.force_authenticate(user=self.manager)
        manager_response = api_client.get("/api/v1/licensing/organization/team/")

        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(
            owner_response.data["organization"]["id"],
            self.organization.pk,
        )
        self.assertEqual(owner_response.data["owner"]["email"], self.owner.email)
        self.assertEqual(
            owner_response.data["license_managers"][0]["email"],
            self.manager.email,
        )
        self.assertEqual(
            owner_response.data["pending_invitations"][0]["invitation_id"],
            invitation.pk,
        )
        self.assertEqual(
            owner_response.data["pending_invitations"][0]["email"],
            "pending.manager@example.com",
        )
        self.assertTrue(owner_response.data["permissions"]["can_invite"])
        self.assertEqual(manager_response.status_code, 200)
        self.assertEqual(manager_response.data["current_user_role"], "license_manager")
        self.assertFalse(manager_response.data["permissions"]["can_invite"])

    def test_owner_can_invite_resend_and_revoke_license_manager_invitation(self):
        api_client = APIClient()
        api_client.force_authenticate(user=self.owner)

        created = api_client.post(
            "/api/v1/licensing/organization/invitations/",
            {"email": "new-manager@example.com"},
        )
        first_invitation = OrganizationInvitation.objects.get(
            pk=created.data["invitation_id"]
        )
        resent = api_client.post(
            f"/api/v1/licensing/organization/invitations/{first_invitation.pk}/resend/"
        )
        first_invitation.refresh_from_db()
        replacement = OrganizationInvitation.objects.get(
            pk=resent.data["invitation_id"]
        )
        revoked = api_client.post(
            f"/api/v1/licensing/organization/invitations/{replacement.pk}/revoke/"
        )
        replacement.refresh_from_db()

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["status"], "pending")
        self.assertEqual(resent.status_code, 200)
        self.assertNotEqual(replacement.pk, first_invitation.pk)
        self.assertIsNotNone(first_invitation.revoked_at)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(revoked.data["status"], "revoked")
        self.assertIsNotNone(replacement.revoked_at)

    def test_manager_and_other_organization_cannot_manage_invitations(self):
        invitation, _token = InvitationService.issue(
            organization=self.organization,
            email="protected-manager@example.com",
            invited_by=self.owner,
        )
        other_organization = OrganizationService.create(
            name="Other Invitation Organization",
            owner=self.outsider,
        )
        api_client = APIClient()
        api_client.force_authenticate(user=self.manager)

        manager_invite = api_client.post(
            "/api/v1/licensing/organization/invitations/",
            {"email": "blocked@example.com"},
        )
        manager_revoke = api_client.post(
            f"/api/v1/licensing/organization/invitations/{invitation.pk}/revoke/"
        )
        api_client.force_authenticate(user=self.outsider)
        hidden = api_client.post(
            f"/api/v1/licensing/organization/invitations/{invitation.pk}/resend/"
        )
        own_team = api_client.get("/api/v1/licensing/organization/team/")

        self.assertEqual(manager_invite.status_code, 403)
        self.assertEqual(manager_revoke.status_code, 403)
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(own_team.status_code, 200)
        self.assertEqual(
            own_team.data["organization"]["id"],
            other_organization.pk,
        )

    def test_admin_can_search_and_filter_organization_licenses(self):
        active_license = self.provision(name="Searchable Radio License")
        LicenseLifecycleService.allocate(
            license=active_license,
            product=self.radio,
            order_item=self.radio_order_item,
            quantity=1,
        )
        other_organization = OrganizationService.create(
            name="Filtered Mining Organization",
            owner=self.outsider,
        )
        expired_license = LicenseLifecycleService.provision(
            organization=other_organization,
            license_product=self.license_product,
            name="Expired Mining License",
        )
        License.objects.filter(pk=expired_license.pk).update(
            status=License.Status.EXPIRED,
            expires_on=timezone.localdate() - timedelta(days=1),
        )
        api_client = APIClient()

        anonymous = api_client.get("/api/v1/admin/licensing/organizations/")
        api_client.force_authenticate(user=self.manager)
        forbidden = api_client.get("/api/v1/admin/licensing/organizations/")
        api_client.force_authenticate(user=self.staff)
        searched = api_client.get(
            "/api/v1/admin/licensing/organizations/",
            {"search": "Mining", "status": License.Status.EXPIRED},
        )
        product_filtered = api_client.get(
            "/api/v1/admin/licensing/organizations/",
            {"product": self.license_product.sku},
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(searched.status_code, 200)
        self.assertEqual(searched.data["count"], 1)
        self.assertEqual(
            searched.data["results"][0]["id"],
            other_organization.pk,
        )
        self.assertEqual(
            searched.data["results"][0]["status"],
            License.Status.EXPIRED,
        )
        self.assertEqual(product_filtered.status_code, 200)
        self.assertEqual(product_filtered.data["count"], 2)
        self.assertEqual(
            product_filtered.data["summary"]["organizations_with_licenses"],
            2,
        )
        self.assertEqual(
            product_filtered.data["summary"]["active_licenses"],
            1,
        )
        self.assertEqual(active_license.organization, self.organization)

    def test_admin_organization_detail_reuses_license_allocations_and_history(self):
        license = self.provision(name="Admin Detail License")
        LicenseLifecycleService.allocate(
            license=license,
            product=self.radio,
            order_item=self.radio_order_item,
            quantity=2,
            actor=self.staff,
        )
        api_client = APIClient()
        api_client.force_authenticate(user=self.staff)

        detail = api_client.get(
            f"/api/v1/admin/licensing/organizations/{self.organization.pk}/"
        )
        history = api_client.get(
            f"/api/v1/admin/licensing/organizations/"
            f"{self.organization.pk}/history/"
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["organization"]["id"], self.organization.pk)
        self.assertEqual(detail.data["organization"]["license_manager_count"], 1)
        self.assertEqual(detail.data["summary"]["licensed_product_count"], 1)
        self.assertEqual(detail.data["summary"]["active_quantity"], 2)
        self.assertEqual(len(detail.data["licenses"]), 1)
        self.assertEqual(
            detail.data["licenses"][0]["license_number"],
            license.license_number,
        )
        self.assertEqual(
            detail.data["licenses"][0]["allocations"][0]["source_order"][
                "order_number"
            ],
            self.order.order_number,
        )
        self.assertTrue(detail.data["permissions"]["can_adjust"])
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["count"], 2)
        self.assertEqual(
            {event["kind"] for event in history.data["results"]},
            {LicenseEvent.Type.PROVISIONED, LicenseEvent.Type.ALLOCATED},
        )

    def test_admin_can_send_and_list_audited_organization_notification(self):
        license = self.provision(name="Notification License")
        api_client = APIClient()
        api_client.force_authenticate(user=self.staff)
        url = (
            f"/api/v1/admin/licensing/organizations/"
            f"{self.organization.pk}/notifications/"
        )

        sent = api_client.post(
            url,
            {
                "title": "Renewal review required",
                "message": "Please review the upcoming annual renewal.",
                "license_number": license.license_number,
            },
        )
        listed = api_client.get(url)
        api_client.force_authenticate(user=self.manager)
        forbidden = api_client.post(
            url,
            {"title": "Blocked", "message": "Not allowed"},
        )

        self.assertEqual(sent.status_code, 201)
        self.assertEqual(sent.data["kind"], LicenseEvent.Type.NOTIFICATION_SENT)
        self.assertEqual(sent.data["actor_name"], self.staff.email)
        self.assertEqual(sent.data["license_number"], license.license_number)
        self.assertEqual(UserNotification.objects.count(), 2)
        self.assertSetEqual(
            set(UserNotification.objects.values_list("recipient_id", flat=True)),
            {self.owner.pk, self.manager.pk},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(
            listed.data["results"][0]["message"],
            "Please review the upcoming annual renewal.",
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_admin_adjustment_is_audited_and_scoped_to_organization(self):
        license = self.provision(name="Adjustable License")
        other_organization = OrganizationService.create(
            name="Other Adjustment Organization",
            owner=self.outsider,
        )
        api_client = APIClient()
        api_client.force_authenticate(user=self.staff)
        adjustment_url = (
            f"/api/v1/admin/licensing/organizations/{self.organization.pk}/"
            f"licenses/{license.license_number}/adjust/"
        )

        adjusted = api_client.post(
            adjustment_url,
            {"capacity": 5, "reason": "Approved support increase"},
        )
        wrong_organization = api_client.post(
            f"/api/v1/admin/licensing/organizations/{other_organization.pk}/"
            f"licenses/{license.license_number}/adjust/",
            {"capacity": 6, "reason": "Must remain scoped"},
        )

        license.refresh_from_db()
        event = LicenseEvent.objects.get(
            license=license,
            event_type=LicenseEvent.Type.ADJUSTED,
        )
        self.assertEqual(adjusted.status_code, 200)
        self.assertEqual(adjusted.data["capacity"], 5)
        self.assertEqual(license.capacity, 5)
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.metadata["reason"], "Approved support increase")
        self.assertEqual(wrong_organization.status_code, 404)


class LicenseCompatibilityCapacityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="capacity-owner@example.com",
            email="capacity-owner@example.com",
            password="StrongPass123!",
        )
        self.organization = OrganizationService.create(
            name="Capacity Organization",
            owner=self.owner,
        )
        license_category = Category.objects.create(name="Capacity Licenses")
        product_category = Category.objects.create(name="Capacity Products")
        self.license_product = Product.objects.create(
            category=license_category,
            name="Capacity License",
            sku="CAPACITY-LIC-3",
            price="100.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=3,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )
        self.other_license_product = Product.objects.create(
            category=license_category,
            name="Other Capacity License",
            sku="CAPACITY-OTHER-LIC-5",
            price="120.00",
            licensing_role=Product.LicensingRole.LICENSE_PRODUCT,
            license_capacity=5,
            license_term_days=365,
            status=Product.Status.PUBLISHED,
        )
        self.radio = Product.objects.create(
            category=product_category,
            name="Capacity Radio",
            sku="CAPACITY-RADIO",
            price="250.00",
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.license_product,
            status=Product.Status.PUBLISHED,
        )
        self.second_radio = Product.objects.create(
            category=product_category,
            name="Second Capacity Radio",
            sku="CAPACITY-RADIO-2",
            price="275.00",
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.license_product,
            status=Product.Status.PUBLISHED,
        )
        self.other_radio = Product.objects.create(
            category=product_category,
            name="Other Capacity Radio",
            sku="CAPACITY-OTHER-RADIO",
            price="300.00",
            licensing_role=Product.LicensingRole.LICENSED_PRODUCT,
            required_license_product=self.other_license_product,
            status=Product.Status.PUBLISHED,
        )
        self.standard_product = Product.objects.create(
            category=product_category,
            name="Standard Accessory",
            sku="CAPACITY-STANDARD",
            price="25.00",
            status=Product.Status.PUBLISHED,
        )

    def create_license(
        self,
        *,
        license_product=None,
        status=License.Status.ACTIVE,
        expires_on=None,
        used_capacity=0,
    ):
        license = LicenseLifecycleService.provision(
            organization=self.organization,
            license_product=license_product or self.license_product,
        )
        License.objects.filter(pk=license.pk).update(
            status=status,
            expires_on=expires_on or license.expires_on,
            used_capacity=used_capacity,
        )
        license.refresh_from_db()
        return license

    def test_compatibility_resolves_only_for_licensed_products(self):
        self.assertEqual(
            ProductLicenseCompatibilityService.required_license_product(self.radio),
            self.license_product,
        )
        self.assertTrue(
            ProductLicenseCompatibilityService.are_compatible(
                product=self.radio,
                license_product=self.license_product,
            )
        )
        self.assertIsNone(
            ProductLicenseCompatibilityService.required_license_product(
                self.standard_product
            )
        )
        self.assertIsNone(
            ProductLicenseCompatibilityService.required_license_product(
                self.license_product
            )
        )

    def test_capacity_lookup_uses_earliest_expiry_and_ignores_ineligible_licenses(self):
        today = timezone.localdate()
        later = self.create_license(expires_on=today + timedelta(days=20))
        early = self.create_license(
            expires_on=today + timedelta(days=10),
            used_capacity=2,
        )
        self.create_license(expires_on=today - timedelta(days=1))
        self.create_license(
            status=License.Status.CANCELLED,
            expires_on=today + timedelta(days=5),
        )
        self.create_license(
            license_product=self.other_license_product,
            expires_on=today + timedelta(days=2),
        )

        result = LicenseCapacityService.for_product(
            organization=self.organization,
            product=self.radio,
            requested_quantity=3,
            on_date=today,
        )

        self.assertEqual(result.total_capacity, 6)
        self.assertEqual(result.used_capacity, 2)
        self.assertEqual(result.available_capacity, 4)
        self.assertEqual(result.covered_quantity, 3)
        self.assertEqual(result.uncovered_quantity, 0)
        self.assertEqual(result.required_license_units, 0)
        self.assertEqual(
            [slot.license for slot in result.coverage_plan],
            [early, later],
        )
        self.assertEqual(
            [slot.covered_quantity for slot in result.coverage_plan],
            [1, 2],
        )

    def test_lookup_calculates_uncovered_quantity_and_license_units(self):
        self.create_license(used_capacity=2)

        result = LicenseCapacityService.for_product(
            organization=self.organization,
            product=self.radio,
            requested_quantity=8,
        )

        self.assertEqual(result.available_capacity, 1)
        self.assertEqual(result.covered_quantity, 1)
        self.assertEqual(result.uncovered_quantity, 7)
        self.assertEqual(result.required_license_units, 3)

    def test_lookup_without_organization_requires_new_license_capacity(self):
        result = LicenseCapacityService.for_product(
            organization=None,
            product=self.radio,
            requested_quantity=4,
        )

        self.assertEqual(result.total_capacity, 0)
        self.assertEqual(result.covered_quantity, 0)
        self.assertEqual(result.uncovered_quantity, 4)
        self.assertEqual(result.required_license_units, 2)

    def test_grouped_requirements_share_capacity_for_compatible_products(self):
        self.create_license(used_capacity=1)
        self.create_license(license_product=self.other_license_product)

        requirements = LicenseCapacityService.requirements_for_products(
            organization=self.organization,
            product_quantities=(
                (self.radio, 3),
                (self.second_radio, 4),
                (self.standard_product, 5),
                (self.license_product, 1),
            ),
        )

        self.assertEqual(len(requirements), 1)
        result = requirements[0]
        self.assertEqual(result.license_product, self.license_product)
        self.assertEqual(result.requested_quantity, 7)
        self.assertEqual(result.available_capacity, 2)
        self.assertEqual(result.uncovered_quantity, 5)
        self.assertEqual(result.required_license_units, 2)
        self.assertEqual(
            [(item.product, item.quantity) for item in result.product_quantities],
            [(self.radio, 3), (self.second_radio, 4)],
        )

    def test_grouped_requirements_keep_different_license_pools_separate(self):
        requirements = LicenseCapacityService.requirements_for_products(
            organization=self.organization,
            product_quantities=((self.radio, 2), (self.other_radio, 7)),
        )

        by_license_product = {item.license_product: item for item in requirements}
        self.assertEqual(by_license_product[self.license_product].required_license_units, 1)
        self.assertEqual(
            by_license_product[self.other_license_product].required_license_units,
            2,
        )

    def test_negative_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            LicenseCapacityService.for_product(
                organization=self.organization,
                product=self.radio,
                requested_quantity=-1,
            )
