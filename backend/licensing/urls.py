from django.urls import path

from licensing.views import (
    CartCapacityView,
    ClientLicenseDetailView,
    LicenseAdjustmentView,
    OrganizationInvitationCreateView,
    OrganizationInvitationResendView,
    OrganizationInvitationRevokeView,
    OrganizationLicenseListView,
    OrganizationSummaryView,
    OrganizationTeamView,
)


urlpatterns = [
    path("cart-capacity/", CartCapacityView.as_view(), name="licensing-cart-capacity"),
    path(
        "organization/summary/",
        OrganizationSummaryView.as_view(),
        name="licensing-organization-summary",
    ),
    path(
        "organization/licenses/",
        OrganizationLicenseListView.as_view(),
        name="licensing-organization-license-list",
    ),
    path(
        "organization/team/",
        OrganizationTeamView.as_view(),
        name="licensing-organization-team",
    ),
    path(
        "organization/invitations/",
        OrganizationInvitationCreateView.as_view(),
        name="licensing-organization-invitation-create",
    ),
    path(
        "organization/invitations/<int:pk>/resend/",
        OrganizationInvitationResendView.as_view(),
        name="licensing-organization-invitation-resend",
    ),
    path(
        "organization/invitations/<int:pk>/revoke/",
        OrganizationInvitationRevokeView.as_view(),
        name="licensing-organization-invitation-revoke",
    ),
    path(
        "licenses/<str:license_number>/",
        ClientLicenseDetailView.as_view(),
        name="licensing-license-detail",
    ),
    path(
        "licenses/<int:pk>/adjust/",
        LicenseAdjustmentView.as_view(),
        name="licensing-license-adjust",
    ),
]
