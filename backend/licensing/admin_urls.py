from django.urls import path

from licensing.admin_views import (
    AdminOrganizationLicenseAdjustmentView,
    AdminOrganizationLicenseDetailView,
    AdminOrganizationLicenseHistoryView,
    AdminOrganizationLicenseListView,
    AdminOrganizationLicenseNotificationView,
)


urlpatterns = [
    path(
        "organizations/",
        AdminOrganizationLicenseListView.as_view(),
        name="admin-licensing-organization-list",
    ),
    path(
        "organizations/<int:organization_id>/",
        AdminOrganizationLicenseDetailView.as_view(),
        name="admin-licensing-organization-detail",
    ),
    path(
        "organizations/<int:organization_id>/history/",
        AdminOrganizationLicenseHistoryView.as_view(),
        name="admin-licensing-organization-history",
    ),
    path(
        "organizations/<int:organization_id>/notifications/",
        AdminOrganizationLicenseNotificationView.as_view(),
        name="admin-licensing-organization-notifications",
    ),
    path(
        "organizations/<int:organization_id>/licenses/"
        "<str:license_number>/adjust/",
        AdminOrganizationLicenseAdjustmentView.as_view(),
        name="admin-licensing-organization-license-adjust",
    ),
]
