from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.models import Banner, ContactMessage, Promotion, SiteSetting, UserNotification
from common.validators import validate_phone


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = (
            "id",
            "title",
            "subtitle",
            "description",
            "cta_label",
            "cta_url",
            "image_url",
            "sort_order",
            "is_active",
        )


class SiteSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSetting
        fields = (
            "site_name",
            "tagline",
            "support_email",
            "support_phone",
            "company_address",
            "facebook_url",
            "twitter_url",
            "linkedin_url",
            "instagram_url",
            "commerce_defaults_enabled",
            "default_currency",
            "tax_rate",
            "flat_shipping_rate",
            "free_shipping_minimum",
            "bank_transfer_enabled",
            "bank_beneficiary_name",
            "bank_name",
            "bank_account_number",
            "bank_iban",
            "bank_swift_bic",
            "bank_payment_instructions",
            "working_hours",
            "about_story",
            "about_mission",
            "about_vision",
            "about_image_url",
            "about_team",
            "about_values",
            "about_stats",
            "meta_title",
            "meta_description",
            "homepage_hero_secondary_cta_label",
            "homepage_hero_secondary_cta_url",
            "homepage_hero_stats",
            "homepage_solution_eyebrow",
            "homepage_solution_title",
            "homepage_solution_description",
            "homepage_solution_benefits",
            "homepage_comparison_eyebrow",
            "homepage_comparison_title",
            "homepage_comparison_products",
            "homepage_resources_eyebrow",
            "homepage_resources_title",
            "homepage_resources",
            "homepage_contact_eyebrow",
            "homepage_contact_title",
            "homepage_contact_description",
            "homepage_contact_cta_label",
            "homepage_contact_cta_url",
        )
class ContactMessageSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(required=False, allow_blank=True, validators=[validate_phone])
    class Meta:
        model = ContactMessage
        fields = ("id", "name", "email", "phone", "subject", "message", "is_read", "created_at")
        read_only_fields = ("id", "is_read", "created_at")


class UserNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserNotification
        fields = ("id", "title", "message", "url", "is_read", "created_at")
        read_only_fields = fields


class PromotionSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    class Meta:
        model = Promotion
        fields = (
            "id",
            "code",
            "title",
            "description",
            "discount_type",
            "discount_value",
            "starts_at",
            "ends_at",
            "usage_limit",
            "times_redeemed",
            "is_active",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("times_redeemed", "created_at", "updated_at", "status")

    def validate(self, attrs):
        discount_type = attrs.get(
            "discount_type",
            getattr(self.instance, "discount_type", Promotion.DiscountType.PERCENTAGE),
        )
        discount_value = attrs.get(
            "discount_value",
            getattr(self.instance, "discount_value", None),
        )
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if discount_type == Promotion.DiscountType.PERCENTAGE and discount_value and discount_value > 100:
            raise serializers.ValidationError({"discount_value": "Percentage cannot exceed 100."})
        if starts_at and ends_at and starts_at >= ends_at:
            raise serializers.ValidationError({"ends_at": "End date must be after start date."})
        return attrs

    @extend_schema_field(serializers.CharField)
    def get_status(self, obj) -> str:
        now = timezone.now()
        if not obj.is_active:
            return "inactive"
        if obj.starts_at and obj.starts_at > now:
            return "scheduled"
        if obj.ends_at and obj.ends_at < now:
            return "expired"
        if obj.usage_limit is not None and obj.times_redeemed >= obj.usage_limit:
            return "redeemed"
        return "active"
