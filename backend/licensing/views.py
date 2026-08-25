from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from licensing.serializers import (
    CartCapacityRequestSerializer,
    CartCapacityRequirementSerializer,
    ClientLicenseDetailSerializer,
    ClientLicenseListSerializer,
    LicenseRenewalSummarySerializer,
    LicenseAdjustmentSerializer,
    LicenseSummarySerializer,
    OrganizationInvitationAcceptSerializer,
    OrganizationInvitationAcceptanceSerializer,
    OrganizationInvitationCreateSerializer,
    OrganizationInvitationSerializer,
    OrganizationOwnershipTransferSerializer,
    OrganizationCreateSerializer,
    OrganizationSummarySerializer,
    OrganizationTeamSerializer,
    OrganizationWorkspaceListSerializer,
    OrganizationSettingsSerializer,
)
from licensing.models import License, Organization, OrganizationInvitation
from licensing.permissions import OrganizationAccessPolicy
from licensing.services import (
    CartLicenseService,
    ClientLicenseDetailService,
    InvitationService,
    LicenseLifecycleService,
    LicenseRenewalOrderService,
    OrganizationLicenseListService,
    OrganizationSummaryService,
    OrganizationService,
    OrganizationOwnershipService,
    OrganizationTeamService,
)


def _raise_api_validation(exc):
    detail = getattr(exc, "message_dict", None) or {
        "detail": exc.messages
    }
    raise ValidationError(detail) from exc


def _invitation_payload(invitation, *, accept_url=None):
    payload = {
        "invitation_id": invitation.pk,
        "email": invitation.email,
        "role": invitation.role,
        "status": invitation.status,
        "expires_at": invitation.expires_at,
    }
    if accept_url:
        payload["accept_url"] = accept_url
    return payload


def _requested_organization_id(request):
    value = request.query_params.get("organization")
    if value in (None, ""):
        return None
    try:
        organization_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"organization": "Use a valid organization id."}) from exc
    if organization_id < 1:
        raise ValidationError({"organization": "Use a valid organization id."})
    return organization_id


class CartCapacityView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="Calculate required license capacity",
        request=CartCapacityRequestSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = CartCapacityRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_quantities = (
            (item["product"], item["quantity"])
            for item in serializer.validated_data["items"]
        )
        organization, requirements = CartLicenseService.calculate(
            user=request.user,
            product_quantities=product_quantities,
        )
        payload = []
        for requirement in requirements:
            capacity = requirement.capacity
            payload.append(
                {
                    "license_product": capacity.license_product,
                    "product_quantities": [
                        {
                            "product_id": item.product.pk,
                            "product_name": item.product.name,
                            "quantity": item.quantity,
                        }
                        for item in capacity.product_quantities
                    ],
                    "requested_quantity": capacity.requested_quantity,
                    "covered_quantity": capacity.covered_quantity,
                    "uncovered_quantity": capacity.uncovered_quantity,
                    "available_capacity": capacity.available_capacity,
                    "required_license_units": capacity.required_license_units,
                    "provided_license_units": requirement.provided_license_units,
                    "automatic_license_units": requirement.automatic_license_units,
                }
            )
        response_serializer = CartCapacityRequirementSerializer(
            payload,
            many=True,
            context={"request": request},
        )
        return Response(
            {
                "organization": (
                    {
                        "public_id": str(organization.public_id),
                        "name": organization.name,
                    }
                    if organization
                    else None
                ),
                "requirements": response_serializer.data,
            }
        )


class LicenseAdjustmentView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        summary="Adjust a license",
        request=LicenseAdjustmentSerializer,
        responses=LicenseSummarySerializer,
    )
    def post(self, request, pk):
        license = get_object_or_404(License.objects.all(), pk=pk)
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
            detail = getattr(exc, "message_dict", None) or {
                "adjustment": exc.messages
            }
            raise ValidationError(detail) from exc
        return Response(LicenseSummarySerializer(adjusted).data)


class OrganizationSummaryView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Get the current organization license summary",
        responses=OrganizationSummarySerializer,
    )
    def get(self, request):
        summary = OrganizationSummaryService.for_user(
            request.user,
            organization_id=_requested_organization_id(request),
        )
        if summary is None:
            return Response(
                {"detail": "No active organization membership was found."},
                status=404,
            )
        return Response(OrganizationSummarySerializer(summary).data)


class OrganizationLicenseListView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="List the current organization's licenses",
        responses=ClientLicenseListSerializer,
    )
    def get(self, request):
        payload = OrganizationLicenseListService.for_user(
            request.user,
            organization_id=_requested_organization_id(request),
        )
        if payload is None:
            return Response(
                {"detail": "No active organization membership was found."},
                status=404,
            )
        return Response(ClientLicenseListSerializer(payload).data)


class ClientLicenseDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Get organization license details",
        responses=ClientLicenseDetailSerializer,
    )
    def get(self, request, license_number):
        payload = ClientLicenseDetailService.for_user(
            user=request.user,
            license_number=license_number,
            organization_id=_requested_organization_id(request),
        )
        if payload is None:
            return Response({"detail": "License not found."}, status=404)
        return Response(ClientLicenseDetailSerializer(payload).data)


class LicenseRenewalOrderView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Get the selected license renewal payment summary",
        responses=LicenseRenewalSummarySerializer,
    )
    def get(self, request, license_number):
        payload = LicenseRenewalOrderService.summary(
            user=request.user,
            license_number=license_number,
            organization_id=_requested_organization_id(request),
        )
        return Response(LicenseRenewalSummarySerializer(payload).data)


class OrganizationTeamView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="List organization owners, managers, and invitations",
        responses=OrganizationTeamSerializer,
    )
    def get(self, request):
        payload = OrganizationTeamService.for_user(
            request.user,
            organization_id=_requested_organization_id(request),
        )
        if payload is None:
            return Response(
                {"detail": "No active organization membership was found."},
                status=404,
            )
        return Response(OrganizationTeamSerializer(payload).data)


class OrganizationOwnershipTransferView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Transfer organization ownership to a License Manager",
        request=OrganizationOwnershipTransferSerializer,
        responses=OrganizationTeamSerializer,
    )
    def post(self, request):
        membership = OrganizationSummaryService.membership_for_user(
            request.user,
            organization_id=_requested_organization_id(request),
        )
        if membership is None:
            return Response(
                {"detail": "No active organization membership was found."},
                status=404,
            )
        serializer = OrganizationOwnershipTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            OrganizationOwnershipService.transfer(
                organization=membership.organization,
                target_membership_id=serializer.validated_data["membership_id"],
                transferred_by=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        payload = OrganizationTeamService.for_user(
            request.user,
            organization_id=membership.organization_id,
        )
        return Response(OrganizationTeamSerializer(payload).data)


class OrganizationInvitationCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Invite an organization license manager",
        request=OrganizationInvitationCreateSerializer,
        responses={201: OrganizationInvitationSerializer},
    )
    def post(self, request):
        membership = OrganizationSummaryService.membership_for_user(
            request.user,
            organization_id=_requested_organization_id(request),
        )
        if membership is None:
            return Response(
                {"detail": "No active organization membership was found."},
                status=404,
            )
        serializer = OrganizationInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invitation, token = InvitationService.issue(
                organization=membership.organization,
                email=serializer.validated_data["email"],
                invited_by=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(
            OrganizationInvitationSerializer(
                _invitation_payload(invitation, accept_url=InvitationService.accept_url(token))
            ).data,
            status=201,
        )


class OrganizationInvitationAcceptView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Accept an organization License Manager invitation",
        request=OrganizationInvitationAcceptSerializer,
        responses=OrganizationInvitationAcceptanceSerializer,
    )
    def post(self, request):
        serializer = OrganizationInvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = InvitationService.accept(
                token=serializer.validated_data["token"],
                user=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(
            OrganizationInvitationAcceptanceSerializer(
                {
                    "organization_id": membership.organization_id,
                    "organization_name": membership.organization.name,
                    "role": membership.role,
                }
            ).data
        )


class OrganizationInvitationActionView(APIView):
    permission_classes = (IsAuthenticated,)
    action = None

    @extend_schema(
        summary="Resend or revoke an organization invitation",
        request=None,
        responses=OrganizationInvitationSerializer,
    )
    def post(self, request, pk):
        membership = OrganizationSummaryService.membership_for_user(
            request.user,
            organization_id=_requested_organization_id(request),
        )
        if membership is None:
            return Response(
                {"detail": "No active organization membership was found."},
                status=404,
            )
        invitation = get_object_or_404(
            OrganizationInvitation.objects.select_related("organization"),
            pk=pk,
            organization=membership.organization,
        )
        try:
            if self.action == "resend":
                invitation, token = InvitationService.resend(
                    invitation=invitation,
                    resent_by=request.user,
                )
            else:
                invitation = InvitationService.revoke(
                    invitation=invitation,
                    revoked_by=request.user,
                )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        payload = _invitation_payload(
            invitation,
            accept_url=(InvitationService.accept_url(token) if self.action == "resend" else None),
        )
        return Response(OrganizationInvitationSerializer(payload).data)


class OrganizationInvitationResendView(OrganizationInvitationActionView):
    action = "resend"


class OrganizationInvitationRevokeView(OrganizationInvitationActionView):
    action = "revoke"


class OrganizationWorkspaceListView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="List organizations available to the signed-in user",
        responses=OrganizationWorkspaceListSerializer,
    )
    def get(self, request):
        return Response(
            OrganizationWorkspaceListSerializer(
                OrganizationSummaryService.workspaces_for_user(request.user)
            ).data
        )

    @extend_schema(
        summary="Create the signed-in user's first organization",
        request=OrganizationCreateSerializer,
        responses={201: OrganizationWorkspaceListSerializer},
    )
    def post(self, request):
        if OrganizationSummaryService.membership_for_user(request.user) is not None:
            raise ValidationError(
                {"organization": "Your account already belongs to an organization."}
            )

        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            OrganizationService.create(
                name=serializer.validated_data["name"],
                owner=request.user,
                billing_email=serializer.validated_data.get("billing_email", request.user.email),
                created_by=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)

        return Response(
            OrganizationWorkspaceListSerializer(
                OrganizationSummaryService.workspaces_for_user(request.user)
            ).data,
            status=201,
        )


class OrganizationSettingsView(APIView):
    permission_classes = (IsAuthenticated,)

    def _membership(self, request):
        membership = OrganizationSummaryService.membership_for_user(
            request.user,
            organization_id=_requested_organization_id(request),
        )
        if membership is None:
            raise ValidationError({"organization": "Select an organization you belong to."})
        return membership

    @extend_schema(summary="Get editable organization settings", responses=OrganizationSettingsSerializer)
    def get(self, request):
        organization = self._membership(request).organization
        return Response(OrganizationSettingsSerializer({
            "id": organization.pk,
            "name": organization.name,
            "billing_email": organization.billing_email,
            "status": organization.status,
        }).data)

    @extend_schema(
        summary="Update organization settings as Owner",
        request=OrganizationSettingsSerializer,
        responses=OrganizationSettingsSerializer,
    )
    def patch(self, request):
        membership = self._membership(request)
        organization = membership.organization
        if membership.role != "owner" or not OrganizationAccessPolicy.can_manage_team(
            user=request.user,
            organization=organization,
        ):
            raise ValidationError({"organization": "Only the Organization Owner can edit organization settings."})
        serializer = OrganizationSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "name" in serializer.validated_data:
            name = serializer.validated_data["name"].strip()
            if not name:
                raise ValidationError({"name": "Enter an organization name."})
            organization.name = name
        if "billing_email" in serializer.validated_data:
            organization.billing_email = serializer.validated_data["billing_email"].strip().casefold()
        organization.save()
        return Response(OrganizationSettingsSerializer({
            "id": organization.pk,
            "name": organization.name,
            "billing_email": organization.billing_email,
            "status": organization.status,
        }).data)
