from rest_framework import serializers

from products.models import Product
from products.serializers import ProductSerializer

from licensing.models import License, LicenseEvent


class CartCapacityItemSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.public())
    quantity = serializers.IntegerField(min_value=1, max_value=999)


class CartCapacityRequestSerializer(serializers.Serializer):
    items = CartCapacityItemSerializer(many=True, allow_empty=True)


class CartCapacityProductQuantitySerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    quantity = serializers.IntegerField()


class CartCapacityRequirementSerializer(serializers.Serializer):
    license_product = ProductSerializer()
    product_quantities = CartCapacityProductQuantitySerializer(many=True)
    requested_quantity = serializers.IntegerField()
    covered_quantity = serializers.IntegerField()
    uncovered_quantity = serializers.IntegerField()
    available_capacity = serializers.IntegerField()
    required_license_units = serializers.IntegerField()
    provided_license_units = serializers.IntegerField()
    automatic_license_units = serializers.IntegerField()


class LicenseSummarySerializer(serializers.ModelSerializer):
    remaining_days = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = License
        fields = (
            "id",
            "license_number",
            "name",
            "status",
            "capacity",
            "used_capacity",
            "remaining_days",
            "starts_on",
            "expires_on",
            "renews_on",
            "organization",
            "license_product",
        )
        read_only_fields = fields


class LicenseAdjustmentSerializer(serializers.Serializer):
    capacity = serializers.IntegerField(min_value=1, required=False)
    status = serializers.ChoiceField(choices=License.Status.choices, required=False)
    reason = serializers.CharField(max_length=500, trim_whitespace=True)

    def validate(self, attrs):
        if "capacity" not in attrs and "status" not in attrs:
            raise serializers.ValidationError(
                "Provide a capacity or status adjustment."
            )
        return attrs


class OrganizationIdentitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    public_id = serializers.UUIDField()
    name = serializers.CharField()
    billing_email = serializers.EmailField(allow_blank=True)
    current_user_role = serializers.ChoiceField(
        choices=("owner", "license_manager")
    )


class OrganizationLicenseSummarySerializer(serializers.Serializer):
    license_count = serializers.IntegerField()
    active_license_count = serializers.IntegerField()
    expiring_soon_count = serializers.IntegerField()
    expired_license_count = serializers.IntegerField()
    total_capacity = serializers.IntegerField()
    used_capacity = serializers.IntegerField()
    available_capacity = serializers.IntegerField()
    next_expiry = serializers.DateField(allow_null=True)
    next_expiry_remaining_days = serializers.IntegerField(allow_null=True)


class OrganizationOwnerSummarySerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()


class OrganizationTeamSummarySerializer(serializers.Serializer):
    owner = OrganizationOwnerSummarySerializer(allow_null=True)
    license_manager_count = serializers.IntegerField()
    pending_invitation_count = serializers.IntegerField()


class OrganizationSummarySerializer(serializers.Serializer):
    organization = OrganizationIdentitySerializer()
    summary = OrganizationLicenseSummarySerializer()
    team = OrganizationTeamSummarySerializer()


class ClientLicenseListOrganizationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    public_id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=("owner", "license_manager"))


class ClientLicenseListItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    license_number = serializers.CharField()
    name = serializers.CharField()
    plan_name = serializers.CharField()
    plan_sku = serializers.CharField()
    status = serializers.ChoiceField(choices=License.Status.choices)
    capacity = serializers.IntegerField()
    used_capacity = serializers.IntegerField()
    available_capacity = serializers.IntegerField()
    capacity_percentage = serializers.IntegerField()
    starts_on = serializers.DateField(allow_null=True)
    expires_on = serializers.DateField(allow_null=True)
    renews_on = serializers.DateField(allow_null=True)
    remaining_days = serializers.IntegerField(allow_null=True)


class ClientRenewalRequestSerializer(serializers.Serializer):
    issued = serializers.BooleanField()
    issued_at = serializers.DateTimeField(allow_null=True)


class ClientLicenseListSerializer(serializers.Serializer):
    organization = ClientLicenseListOrganizationSerializer()
    summary = OrganizationLicenseSummarySerializer()
    licenses = ClientLicenseListItemSerializer(many=True)
    renewal_request = ClientRenewalRequestSerializer()


class SourceOrderSerializer(serializers.Serializer):
    order_number = serializers.CharField()
    ordered_at = serializers.DateTimeField()


class LicenseAllocationProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    sku = serializers.CharField()


class ClientLicenseAllocationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    product = LicenseAllocationProductSerializer()
    quantity = serializers.IntegerField()
    source_order = SourceOrderSerializer()


class ClientLicenseSubscriptionSerializer(serializers.Serializer):
    term_days = serializers.IntegerField(allow_null=True)
    starts_on = serializers.DateField(allow_null=True)
    expires_on = serializers.DateField(allow_null=True)
    renews_on = serializers.DateField(allow_null=True)
    remaining_days = serializers.IntegerField(allow_null=True)
    source_order = SourceOrderSerializer(allow_null=True)


class ClientLicenseDetailSerializer(serializers.Serializer):
    license_number = serializers.CharField()
    name = serializers.CharField()
    plan_name = serializers.CharField()
    plan_sku = serializers.CharField()
    status = serializers.ChoiceField(choices=License.Status.choices)
    capacity = serializers.IntegerField()
    used_capacity = serializers.IntegerField()
    available_capacity = serializers.IntegerField()
    starts_on = serializers.DateField(allow_null=True)
    expires_on = serializers.DateField(allow_null=True)
    renews_on = serializers.DateField(allow_null=True)
    remaining_days = serializers.IntegerField(allow_null=True)
    subscription = ClientLicenseSubscriptionSerializer()
    allocations = ClientLicenseAllocationSerializer(many=True)


class LicenseRenewalSummarySerializer(serializers.Serializer):
    license_number = serializers.CharField()
    license_name = serializers.CharField()
    organization_id = serializers.IntegerField()
    organization_name = serializers.CharField()
    current_expires_on = serializers.DateField(allow_null=True)
    projected_expires_on = serializers.DateField()
    term_days = serializers.IntegerField()
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    product_sku = serializers.CharField()
    product_image_url = serializers.CharField(allow_blank=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class OrganizationTeamIdentitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class OrganizationTeamOwnerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()


class OrganizationLicenseManagerSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=("license_manager",))
    status = serializers.ChoiceField(choices=("active",))


class OrganizationInvitationSerializer(serializers.Serializer):
    invitation_id = serializers.IntegerField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=("license_manager",))
    status = serializers.CharField()
    expires_at = serializers.DateTimeField()
    accept_url = serializers.URLField(required=False)


class OrganizationTeamPermissionsSerializer(serializers.Serializer):
    can_invite = serializers.BooleanField()
    can_revoke_manager = serializers.BooleanField()
    can_transfer_ownership = serializers.BooleanField()


class OrganizationTeamSerializer(serializers.Serializer):
    organization = OrganizationTeamIdentitySerializer()
    current_user_role = serializers.ChoiceField(
        choices=("owner", "license_manager")
    )
    owner = OrganizationTeamOwnerSerializer(allow_null=True)
    license_managers = OrganizationLicenseManagerSerializer(many=True)
    pending_invitations = OrganizationInvitationSerializer(many=True)
    permissions = OrganizationTeamPermissionsSerializer()


class AdminOrganizationMemberSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=("owner", "license_manager"))
    status = serializers.ChoiceField(choices=("active",))


class AdminOrganizationUsersSerializer(serializers.Serializer):
    organization = OrganizationTeamIdentitySerializer()
    owner = AdminOrganizationMemberSerializer(allow_null=True)
    license_managers = AdminOrganizationMemberSerializer(many=True)
    pending_invitations = OrganizationInvitationSerializer(many=True)


class OrganizationOwnershipTransferSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField(min_value=1)


class OrganizationInvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class OrganizationWorkspaceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=("owner", "license_manager"))


class OrganizationWorkspaceListSerializer(serializers.Serializer):
    organizations = OrganizationWorkspaceSerializer(many=True)
    default_organization_id = serializers.IntegerField(allow_null=True)


class OrganizationInvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=20, max_length=255)


class OrganizationInvitationAcceptanceSerializer(serializers.Serializer):
    organization_id = serializers.IntegerField()
    organization_name = serializers.CharField()
    role = serializers.ChoiceField(choices=("license_manager",))


class AdminOrganizationLicenseQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=255)
    status = serializers.ChoiceField(
        choices=License.Status.choices,
        required=False,
        allow_blank=True,
    )
    product = serializers.CharField(required=False, allow_blank=True, max_length=120)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


class AdminLicenseManagementSummarySerializer(serializers.Serializer):
    organizations_with_licenses = serializers.IntegerField()
    active_licenses = serializers.IntegerField()
    licenses_expiring_in_60_days = serializers.IntegerField()
    payments_in_review = serializers.IntegerField()


class AdminOrganizationOwnerSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()


class AdminOrganizationLicenseRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    owner = AdminOrganizationOwnerSerializer(allow_null=True)
    license_count = serializers.IntegerField()
    used_capacity = serializers.IntegerField()
    total_capacity = serializers.IntegerField()
    next_expiry = serializers.DateField(allow_null=True)
    status = serializers.ChoiceField(choices=License.Status.choices)


class AdminOrganizationLicenseListSerializer(serializers.Serializer):
    summary = AdminLicenseManagementSummarySerializer()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AdminOrganizationLicenseRowSerializer(many=True)


class AdminOrganizationDetailIdentitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    owner = AdminOrganizationOwnerSerializer(allow_null=True)
    license_manager_count = serializers.IntegerField()


class AdminOrganizationDetailSummarySerializer(serializers.Serializer):
    subscription_starts_on = serializers.DateField(allow_null=True)
    subscription_expires_on = serializers.DateField(allow_null=True)
    licensed_product_count = serializers.IntegerField()
    active_quantity = serializers.IntegerField()
    status = serializers.ChoiceField(choices=License.Status.choices)


class AdminOrganizationNotificationSummarySerializer(serializers.Serializer):
    renewal_reminder_scheduled_for = serializers.DateField(allow_null=True)
    renewal_invoice_status = serializers.CharField()


class AdminLicenseEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=LicenseEvent.Type.choices)
    message = serializers.CharField()
    actor_name = serializers.CharField()
    license_number = serializers.CharField(allow_null=True)
    metadata = serializers.JSONField()
    created_at = serializers.DateTimeField()


class AdminOrganizationPermissionsSerializer(serializers.Serializer):
    can_adjust = serializers.BooleanField()
    can_send_renewal_invoice = serializers.BooleanField()
    can_send_notification = serializers.BooleanField()


class AdminOrganizationLicenseDetailSerializer(serializers.Serializer):
    organization = AdminOrganizationDetailIdentitySerializer()
    summary = AdminOrganizationDetailSummarySerializer()
    licenses = ClientLicenseDetailSerializer(many=True)
    notifications = AdminOrganizationNotificationSummarySerializer()
    events = AdminLicenseEventSerializer(many=True)
    permissions = AdminOrganizationPermissionsSerializer()


class AdminLicenseEventListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AdminLicenseEventSerializer(many=True)


class AdminOrganizationNotificationCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, trim_whitespace=True)
    message = serializers.CharField(max_length=2000, trim_whitespace=True)
    license_number = serializers.CharField(
        max_length=40,
        required=False,
        allow_blank=True,
    )
