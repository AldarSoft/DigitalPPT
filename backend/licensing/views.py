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
    LicenseAdjustmentSerializer,
    LicenseSummarySerializer,
    OrganizationInvitationCreateSerializer,
    OrganizationInvitationSerializer,
    OrganizationSummarySerializer,
    OrganizationTeamSerializer,
)
from licensing.models import License, OrganizationInvitation
from licensing.services import (
    CartLicenseService,
    ClientLicenseDetailService,
    InvitationService,
    LicenseLifecycleService,
    OrganizationLicenseListService,
    OrganizationSummaryService,
    OrganizationTeamService,
)


def _raise_api_validation(exc):
    detail = getattr(exc, "message_dict", None) or {
        "detail": exc.messages
    }
    raise ValidationError(detail) from exc


def _invitation_payload(invitation):
    return {
        "invitation_id": invitation.pk,
        "email": invitation.email,
        "role": invitation.role,
        "status": invitation.status,
        "expires_at": invitation.expires_at,
    }


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
        summary = OrganizationSummaryService.for_user(request.user)
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
        payload = OrganizationLicenseListService.for_user(request.user)
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
        )
        if payload is None:
            return Response({"detail": "License not found."}, status=404)
        return Response(ClientLicenseDetailSerializer(payload).data)


class OrganizationTeamView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="List organization owners, managers, and invitations",
        responses=OrganizationTeamSerializer,
    )
    def get(self, request):
        payload = OrganizationTeamService.for_user(request.user)
        if payload is None:
            return Response(
                {"detail": "No active organization membership was found."},
                status=404,
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
        membership = OrganizationSummaryService.membership_for_user(request.user)
        if membership is None:
            return Response(
                {"detail": "No active organization membership was found."},
                status=404,
            )
        serializer = OrganizationInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invitation, _token = InvitationService.issue(
                organization=membership.organization,
                email=serializer.validated_data["email"],
                invited_by=request.user,
            )
        except DjangoValidationError as exc:
            _raise_api_validation(exc)
        return Response(
            OrganizationInvitationSerializer(
                _invitation_payload(invitation)
            ).data,
            status=201,
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
        membership = OrganizationSummaryService.membership_for_user(request.user)
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
                invitation, _token = InvitationService.resend(
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
        return Response(
            OrganizationInvitationSerializer(
                _invitation_payload(invitation)
            ).data
        )


class OrganizationInvitationResendView(OrganizationInvitationActionView):
    action = "resend"


class OrganizationInvitationRevokeView(OrganizationInvitationActionView):
    action = "revoke"
