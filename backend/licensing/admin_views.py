from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from common.permissions import CanManageLicenses
from rest_framework.views import APIView

from common.pagination import DefaultPagination
from licensing.admin_services import (
    AdminLicenseNotificationService,
    AdminOrganizationLicenseService,
)
from licensing.models import License, LicenseEvent, Organization, OrganizationInvitation
from licensing.serializers import (
    AdminLicenseEventListSerializer,
    AdminLicenseEventSerializer,
    AdminOrganizationLicenseDetailSerializer,
    AdminOrganizationLicenseListSerializer,
    AdminOrganizationLicenseQuerySerializer,
    AdminOrganizationNotificationCreateSerializer,
    AdminOrganizationUsersSerializer,
    LicenseAdjustmentSerializer,
    LicenseSummarySerializer,
    OrganizationInvitationCreateSerializer,
    OrganizationInvitationSerializer,
    OrganizationOwnershipTransferSerializer,
    AdminOrganizationCreateSerializer,
    AdminOrganizationCreateResponseSerializer,
)
from licensing.services import (
    InvitationService,
    LicenseLifecycleService,
    OrganizationOwnershipService,
    OrganizationService,
)
from users.services import AccountSetupService


def _raise_api_validation(exc):
    detail = getattr(exc, "message_dict", None) or {"detail": exc.messages}
    raise ValidationError(detail) from exc


def _paginated_payload(paginator, rows):
    return {
        "count": paginator.page.paginator.count,
        "next": paginator.get_next_link(),
        "previous": paginator.get_previous_link(),
        "results": rows,
    }


class AdminOrganizationLicenseListView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        operation_id="admin_licensing_organization_list",
        summary="Search and filter organizations with licenses",
        parameters=[AdminOrganizationLicenseQuerySerializer],
        responses=AdminOrganizationLicenseListSerializer,
    )
    def get(self, request):
        query = AdminOrganizationLicenseQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        queryset = AdminOrganizationLicenseService.queryset(
            search=query.validated_data.get("search", "").strip(),
            status=query.validated_data.get("status", ""),
            product=query.validated_data.get("product", "").strip(),
            customer_id=query.validated_data.get("customer_id"),
        )
        paginator = DefaultPagination()
        organizations = paginator.paginate_queryset(queryset, request, view=self)
        payload = _paginated_payload(
            paginator,
            [
                AdminOrganizationLicenseService.organization_row(organization)
                for organization in organizations
            ],
        )
        payload["summary"] = AdminOrganizationLicenseService.summary()
        return Response(AdminOrganizationLicenseListSerializer(payload).data)

    @extend_schema(
        operation_id="admin_licensing_organization_create",
        summary="Create an organization with an Owner or as Draft",
        request=AdminOrganizationCreateSerializer,
        responses={201: AdminOrganizationCreateResponseSerializer},
    )
    @transaction.atomic
    def post(self, request):
        serializer = AdminOrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        mode = data["owner_mode"]
        owner = None
        invitation = None
        token = None
        setup_url = None
        try:
            if mode == AdminOrganizationCreateSerializer.OwnerMode.EXISTING:
                owner = get_object_or_404(
                    get_user_model(),
                    pk=data["existing_owner_id"],
                    is_active=True,
                )
            elif mode == AdminOrganizationCreateSerializer.OwnerMode.CREATE_ACCOUNT:
                owner = AccountSetupService.create_user(
                    email=data["owner_email"],
                    first_name=data.get("owner_first_name", ""),
                    last_name=data.get("owner_last_name", ""),
                    phone_number=data.get("owner_phone", ""),
                )
                setup_url = AccountSetupService.setup_url(owner)

            if owner:
                organization = OrganizationService.create(
                    name=data["name"],
                    owner=owner,
                    billing_email=data.get("billing_email") or owner.email,
                    created_by=request.user,
                )
            else:
                organization = OrganizationService.create_draft(
                    name=data["name"],
                    billing_email=data.get("billing_email", ""),
                    created_by=request.user,
                )
                if mode == AdminOrganizationCreateSerializer.OwnerMode.INVITE:
                    invitation, token = InvitationService.issue(
                        organization=organization,
                        email=data["owner_email"],
                        invited_by=request.user,
                        role="owner",
                    )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)

        payload = {
            "id": organization.pk,
            "name": organization.name,
            "billing_email": organization.billing_email,
            "status": organization.status,
            "owner": (
                {"name": owner.get_full_name().strip() or owner.email, "email": owner.email}
                if owner else None
            ),
            "invitation": (
                {
                    "invitation_id": invitation.pk,
                    "email": invitation.email,
                    "role": invitation.role,
                    "status": invitation.status,
                    "expires_at": invitation.expires_at,
                    "accept_url": InvitationService.accept_url(token),
                }
                if invitation else None
            ),
            "setup_url": setup_url,
        }
        return Response(AdminOrganizationCreateResponseSerializer(payload).data, status=201)


class AdminOrganizationLicenseDetailView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        operation_id="admin_licensing_organization_detail",
        summary="Get organization licensing details",
        responses=AdminOrganizationLicenseDetailSerializer,
    )
    def get(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        payload = AdminOrganizationLicenseService.detail(organization)
        return Response(AdminOrganizationLicenseDetailSerializer(payload).data)


class AdminOrganizationLicenseHistoryView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        operation_id="admin_licensing_organization_history",
        summary="List organization license history",
        responses=AdminLicenseEventListSerializer,
    )
    def get(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        paginator = DefaultPagination()
        events = paginator.paginate_queryset(
            AdminOrganizationLicenseService.event_queryset(organization),
            request,
            view=self,
        )
        payload = _paginated_payload(
            paginator,
            [AdminOrganizationLicenseService.event_row(event) for event in events],
        )
        return Response(AdminLicenseEventListSerializer(payload).data)


class AdminOrganizationLicenseNotificationView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        operation_id="admin_licensing_organization_notifications",
        summary="List organization license notifications",
        responses=AdminLicenseEventListSerializer,
    )
    def get(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        queryset = AdminOrganizationLicenseService.event_queryset(
            organization
        ).filter(event_type=LicenseEvent.Type.NOTIFICATION_SENT)
        paginator = DefaultPagination()
        events = paginator.paginate_queryset(queryset, request, view=self)
        payload = _paginated_payload(
            paginator,
            [AdminOrganizationLicenseService.event_row(event) for event in events],
        )
        return Response(AdminLicenseEventListSerializer(payload).data)

    @extend_schema(
        operation_id="admin_licensing_organization_notification_create",
        summary="Send an organization license notification",
        request=AdminOrganizationNotificationCreateSerializer,
        responses={201: AdminLicenseEventSerializer},
    )
    def post(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        serializer = AdminOrganizationNotificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        license_number = serializer.validated_data.get("license_number", "")
        license = None
        if license_number:
            license = get_object_or_404(
                License,
                organization=organization,
                license_number=license_number,
            )
        try:
            event = AdminLicenseNotificationService.send(
                organization=organization,
                actor=request.user,
                title=serializer.validated_data["title"],
                message=serializer.validated_data["message"],
                license=license,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        payload = AdminOrganizationLicenseService.event_row(
            LicenseEvent.objects.select_related("actor", "license").get(pk=event.pk)
        )
        return Response(AdminLicenseEventSerializer(payload).data, status=201)


class AdminOrganizationRenewalInvoiceView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        operation_id="admin_licensing_organization_renewal_invoice",
        summary="Send an audited renewal invoice notice to an organization",
        request=None,
        responses={201: AdminLicenseEventSerializer},
    )
    def post(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        try:
            event = AdminLicenseNotificationService.send_renewal_invoice(
                organization=organization,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        payload = AdminOrganizationLicenseService.event_row(
            LicenseEvent.objects.select_related("actor", "license").get(pk=event.pk)
        )
        return Response(AdminLicenseEventSerializer(payload).data, status=201)


class AdminOrganizationLicenseAdjustmentView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        operation_id="admin_licensing_organization_license_adjust",
        summary="Make an audited organization license adjustment",
        request=LicenseAdjustmentSerializer,
        responses=LicenseSummarySerializer,
    )
    def post(self, request, organization_id, license_number):
        organization = get_object_or_404(Organization, pk=organization_id)
        license = get_object_or_404(
            License,
            organization=organization,
            license_number=license_number,
        )
        serializer = LicenseAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            adjusted = LicenseLifecycleService.adjust(
                license=license,
                actor=request.user,
                reason=serializer.validated_data["reason"],
                capacity=serializer.validated_data.get("capacity"),
                status=serializer.validated_data.get("status"),
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(LicenseSummarySerializer(adjusted).data)


class AdminOrganizationUsersView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        summary="List organization users and invitations for staff support",
        responses=AdminOrganizationUsersSerializer,
    )
    def get(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        return Response(AdminOrganizationUsersSerializer(
            AdminOrganizationLicenseService.users(organization)
        ).data)


class AdminOrganizationInvitationCreateView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        summary="Invite a License Manager to an organization as staff",
        request=OrganizationInvitationCreateSerializer,
        responses={201: OrganizationInvitationSerializer},
    )
    def post(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        serializer = OrganizationInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invitation, token = InvitationService.issue(
                organization=organization,
                email=serializer.validated_data["email"],
                invited_by=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(OrganizationInvitationSerializer({
            "invitation_id": invitation.pk,
            "email": invitation.email,
            "role": invitation.role,
            "status": invitation.status,
            "expires_at": invitation.expires_at,
            "accept_url": InvitationService.accept_url(token),
        }).data, status=201)


class AdminOrganizationOwnershipTransferView(APIView):
    permission_classes = (CanManageLicenses,)

    @extend_schema(
        summary="Transfer organization ownership to an active License Manager as staff",
        request=OrganizationOwnershipTransferSerializer,
        responses=AdminOrganizationUsersSerializer,
    )
    def post(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        serializer = OrganizationOwnershipTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            OrganizationOwnershipService.transfer(
                organization=organization,
                target_membership_id=serializer.validated_data["membership_id"],
                transferred_by=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        organization.refresh_from_db()
        return Response(AdminOrganizationUsersSerializer(
            AdminOrganizationLicenseService.users(organization)
        ).data)


class AdminOrganizationInvitationActionView(APIView):
    permission_classes = (CanManageLicenses,)
    action = None

    def post(self, request, organization_id, invitation_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        invitation = get_object_or_404(
            OrganizationInvitation.objects.select_related("organization"),
            pk=invitation_id,
            organization=organization,
        )
        try:
            if self.action == "resend":
                invitation, token = InvitationService.resend(
                    invitation=invitation,
                    resent_by=request.user,
                )
                accept_url = InvitationService.accept_url(token)
            else:
                invitation = InvitationService.revoke(
                    invitation=invitation,
                    revoked_by=request.user,
                )
                accept_url = None
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        payload = {
            "invitation_id": invitation.pk,
            "email": invitation.email,
            "role": invitation.role,
            "status": invitation.status,
            "expires_at": invitation.expires_at,
        }
        if accept_url:
            payload["accept_url"] = accept_url
        return Response(OrganizationInvitationSerializer(payload).data)


class AdminOrganizationInvitationResendView(AdminOrganizationInvitationActionView):
    action = "resend"

    @extend_schema(
        operation_id="admin_licensing_organization_invitation_resend",
        summary="Resend an organization invitation as staff",
        request=None,
        responses=OrganizationInvitationSerializer,
    )
    def post(self, request, organization_id, invitation_id):
        return super().post(request, organization_id, invitation_id)


class AdminOrganizationInvitationRevokeView(AdminOrganizationInvitationActionView):
    action = "revoke"

    @extend_schema(
        operation_id="admin_licensing_organization_invitation_revoke",
        summary="Revoke an organization invitation as staff",
        request=None,
        responses=OrganizationInvitationSerializer,
    )
    def post(self, request, organization_id, invitation_id):
        return super().post(request, organization_id, invitation_id)
