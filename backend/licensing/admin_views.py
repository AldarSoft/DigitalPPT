from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.pagination import DefaultPagination
from licensing.admin_services import (
    AdminLicenseNotificationService,
    AdminOrganizationLicenseService,
)
from licensing.models import License, LicenseEvent, Organization
from licensing.serializers import (
    AdminLicenseEventListSerializer,
    AdminLicenseEventSerializer,
    AdminOrganizationLicenseDetailSerializer,
    AdminOrganizationLicenseListSerializer,
    AdminOrganizationLicenseQuerySerializer,
    AdminOrganizationNotificationCreateSerializer,
    LicenseAdjustmentSerializer,
    LicenseSummarySerializer,
)
from licensing.services import LicenseLifecycleService


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
    permission_classes = (IsAdminUser,)

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


class AdminOrganizationLicenseDetailView(APIView):
    permission_classes = (IsAdminUser,)

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
    permission_classes = (IsAdminUser,)

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
    permission_classes = (IsAdminUser,)

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


class AdminOrganizationLicenseAdjustmentView(APIView):
    permission_classes = (IsAdminUser,)

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
