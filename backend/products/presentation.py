"""Validated storefront content and section-level inheritance."""

from copy import deepcopy

from rest_framework import serializers

ICONS = ("truck", "shield-check", "lock-keyhole", "message-circle", "arrow-up-right", "users", "credit-card", "map-pin", "battery", "package", "info")


def default_product_presentation():
    assurances = [
        {"id": "delivery", "icon": "truck", "title": "Delivery quote", "description": "Delivery details are confirmed with your quote.", "active": True},
        {"id": "warranty", "icon": "shield-check", "title": "12-month warranty", "description": "Contact our team for warranty terms and coverage.", "active": True},
        {"id": "payment", "icon": "lock-keyhole", "title": "Secure payment", "description": "Available payment methods are shown at checkout.", "active": True},
    ]
    return {
        "assurances": assurances,
        "radio": {
            "intro": {"eyebrow": "Connected communication", "heading": "Instant voice across the whole country", "description": "", "notice": "Coverage depends on cellular network availability and active service.", "active": True},
            "features": [
                {"id": "voice", "icon": "message-circle", "title": "One-touch communication", "description": "Fast push-to-talk for individuals or teams", "active": True},
                {"id": "range", "icon": "arrow-up-right", "title": "Connected coverage", "description": "Communicate wherever compatible cellular service is available", "active": True},
                {"id": "groups", "icon": "users", "title": "Private and group calls", "description": "Connect individuals and teams", "active": True},
            ],
        },
        "license": {"intro": {"eyebrow": "RadioAdmin service", "heading": "Capacity for your connected radio products", "description": "", "notice": "", "active": True}, "features": []},
        "accessory": {"intro": {"eyebrow": "Accessories", "heading": "Ready for everyday use", "description": "", "notice": "Confirm compatibility before ordering.", "active": True}, "features": []},
    }


class StrictContentSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError("Unknown content fields.")
        return super().to_internal_value(data)


class ContentItemSerializer(StrictContentSerializer):
    id = serializers.SlugField(max_length=64)
    icon = serializers.ChoiceField(choices=ICONS)
    title = serializers.CharField(max_length=80)
    description = serializers.CharField(max_length=500, allow_blank=True)
    active = serializers.BooleanField()


class IntroductionSerializer(StrictContentSerializer):
    eyebrow = serializers.CharField(max_length=80, allow_blank=True)
    heading = serializers.CharField(max_length=160, allow_blank=True)
    description = serializers.CharField(max_length=2000, allow_blank=True)
    notice = serializers.CharField(max_length=500, allow_blank=True)
    active = serializers.BooleanField()


class ContentSectionsSerializer(StrictContentSerializer):
    intro = IntroductionSerializer(required=False)
    features = ContentItemSerializer(many=True, required=False, max_length=8)
    assurances = ContentItemSerializer(many=True, required=False, max_length=3)

    def validate(self, attrs):
        for key in ("features", "assurances"):
            rows = attrs.get(key, [])
            if len({row["id"] for row in rows}) != len(rows):
                raise serializers.ValidationError({key: "Each item must have a unique identifier."})
        if "assurances" in attrs and any(row["id"] not in {"delivery", "warranty", "payment"} for row in attrs["assurances"]):
            raise serializers.ValidationError({"assurances": "Choose delivery, warranty or payment."})
        return attrs


class ProductPresentationDefaultsSerializer(StrictContentSerializer):
    assurances = ContentItemSerializer(many=True, max_length=3)
    radio = ContentSectionsSerializer()
    license = ContentSectionsSerializer()
    accessory = ContentSectionsSerializer()

    def validate(self, attrs):
        if set(attrs) != {"assurances", "radio", "license", "accessory"}:
            raise serializers.ValidationError("Provide assurances and all three templates.")
        check = ContentSectionsSerializer(data={"assurances": attrs["assurances"]})
        check.is_valid(raise_exception=True)
        for layout in ("radio", "license", "accessory"):
            if set(attrs[layout]) != {"intro", "features"}:
                raise serializers.ValidationError({layout: "Provide intro and features."})
        return attrs


def resolve_presentation(product, defaults):
    result = deepcopy(defaults[product.detail_layout])
    result["assurances"] = deepcopy(defaults["assurances"])
    result.update(deepcopy(product.presentation_overrides))
    return result
