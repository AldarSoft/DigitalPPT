from __future__ import annotations

from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from users.models import User, UserProfile
from users.roles import STAFF_ROLE_CHOICES, assign_staff_roles, role_names_for_user
from users.services import AccountSetupService
from users.security import EmailVerificationService
from common.validators import validate_phone


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = (
            "company_name",
            "job_title",
            "avatar_url",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "country",
            "postal_code",
            "use_different_shipping_address",
            "shipping_address_line_1",
            "shipping_address_line_2",
            "shipping_city",
            "shipping_state",
            "shipping_country",
            "shipping_postal_code",
        )


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    staff_roles = serializers.SerializerMethodField()
    staff_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone_number",
            "is_customer",
            "is_staff",
            "is_active",
            "staff_roles",
            "staff_permissions",
            "date_joined",
            "profile",
        )

    def get_staff_roles(self, obj) -> list[str]:
        return role_names_for_user(obj)

    def get_staff_permissions(self, obj) -> list[str]:
        if not obj.is_staff:
            return []
        if obj.is_superuser:
            from users.roles import STAFF_PERMISSIONS

            return sorted(STAFF_PERMISSIONS)
        return sorted(
            permission.removeprefix("users.")
            for permission in obj.get_all_permissions()
            if permission.startswith("users.")
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        email = attrs["email"].strip().casefold()
        matched_user = User.objects.filter(email__iexact=email).first()
        user = authenticate(
            request=request,
            username=matched_user.email if matched_user else email,
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        if not user.is_email_verified:
            raise serializers.ValidationError(
                "Verify your email address before signing in. You can request a new verification email."
            )
        attrs["user"] = user
        return attrs


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "email",
            "password",
            "confirm_password",
            "first_name",
            "last_name",
            "phone_number",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        password_validation.validate_password(attrs["password"])
        return attrs

    def validate_email(self, value):
        normalized = value.strip().casefold()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalized

    def create(self, validated_data):
        password = validated_data.pop("password")
        email = validated_data["email"]
        username_root = email.split("@", 1)[0]
        username = username_root
        counter = 1
        while User.objects.filter(username=username).exists():
            counter += 1
            username = f"{username_root}{counter}"
        user = User.objects.create_user(
            username=username,
            password=password,
            is_customer=True,
            email_verified_at=None,
            **validated_data,
        )
        transaction.on_commit(lambda: EmailVerificationService.send_safely(user))
        return user


class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField()


class EmailVerificationResendSerializer(serializers.Serializer):
    email = serializers.EmailField()


class StaffMfaVerifySerializer(serializers.Serializer):
    challenge = serializers.CharField(max_length=255)
    code = serializers.RegexField(r"^\d{6}$")


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"token": "This reset link is invalid or expired."})

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "This reset link is invalid or expired."})

        password_validation.validate_password(attrs["new_password"], user=user)
        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        if not user.is_email_verified:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["password", "email_verified_at", "updated_at"])
        else:
            user.save(update_fields=["password", "updated_at"])
        return user


class ProfileUpdateSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(required=False)
    phone_number = serializers.CharField(required=False, allow_blank=True, validators=[validate_phone])

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "phone_number",
            "profile",
        )

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if profile_data is not None:
            profile = instance.profile
            for field, value in profile_data.items():
                setattr(profile, field, value)
            profile.save()
        return instance


class AdminUserWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, required=False)
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    staff_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=STAFF_ROLE_CHOICES),
        required=False,
    )
    profile = UserProfileSerializer(required=False)
    phone_number = serializers.CharField(required=False, allow_blank=True, validators=[validate_phone])

    class Meta:
        model = User
        fields = (
            "email",
            "username",
            "password",
            "current_password",
            "first_name",
            "last_name",
            "phone_number",
            "is_customer",
            "is_staff",
            "is_active",
            "staff_roles",
            "profile",
        )

    def validate_email(self, value):
        normalized = value.strip().casefold()
        matches = User.objects.filter(email__iexact=normalized)
        if self.instance:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalized

    def validate_password(self, value):
        password_validation.validate_password(value, user=self.instance)
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        actor = request.user if request else None
        instance = self.instance
        target_is_staff = attrs.get("is_staff", instance.is_staff if instance else False)
        target_was_staff = bool(instance and instance.is_staff)
        roles_supplied = "staff_roles" in attrs
        password_supplied = bool(attrs.get("password"))
        protected_staff_change = target_is_staff or target_was_staff or roles_supplied

        if actor and not actor.is_superuser:
            if protected_staff_change:
                raise serializers.ValidationError({
                    "is_staff": "Only a super administrator can manage staff accounts."
                })
            if password_supplied:
                raise serializers.ValidationError({
                    "password": "Send the customer a password-reset email instead."
                })

        if protected_staff_change:
            if not actor or not actor.is_superuser:
                raise serializers.ValidationError({
                    "is_staff": "Only a super administrator can manage staff accounts."
                })
            current_password = attrs.get("current_password", "")
            if not current_password or not actor.check_password(current_password):
                raise serializers.ValidationError({
                    "current_password": "Enter your current password to change a staff account."
                })
            if not target_is_staff and roles_supplied and attrs.get("staff_roles"):
                raise serializers.ValidationError({
                    "staff_roles": "Customer accounts cannot have staff roles."
                })
            if instance and instance.pk == actor.pk:
                if attrs.get("is_staff") is False or attrs.get("is_active") is False:
                    raise serializers.ValidationError(
                        "You cannot remove your own administrator access."
                    )

        if not instance and target_is_staff and not password_supplied:
            raise serializers.ValidationError({
                "password": "Set an initial password for a new staff account."
            })
        return attrs

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", None)
        validated_data.pop("current_password", None)
        staff_roles = validated_data.pop("staff_roles", [])

        # Customer accounts created by staff must choose their own password from
        # the single-use setup email. Staff accounts retain the existing path.
        is_customer = validated_data.get("is_customer", True)
        is_staff = validated_data.get("is_staff", False)
        if is_customer and not is_staff:
            if password:
                raise serializers.ValidationError(
                    {"password": "Customer accounts use the emailed password setup link."}
                )

            user = AccountSetupService.create_user(
                email=validated_data["email"],
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
                phone_number=validated_data.get("phone_number", ""),
            )
            user.is_active = validated_data.get("is_active", True)
            user.save(update_fields=["is_active", "updated_at"])
            user._account_setup_email_queued = True
        else:
            if is_staff:
                validated_data.setdefault("email_verified_at", timezone.now())
            user = User.objects.create_user(password=password, **validated_data)

        assign_staff_roles(user, staff_roles)

        if profile_data:
            for field, value in profile_data.items():
                setattr(user.profile, field, value)
            user.profile.save()
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        password = validated_data.pop("password", None)
        validated_data.pop("current_password", None)
        staff_roles = validated_data.pop("staff_roles", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()

        if staff_roles is not None:
            assign_staff_roles(instance, staff_roles)

        if profile_data is not None:
            profile = instance.profile
            for field, value in profile_data.items():
                setattr(profile, field, value)
            profile.save()

        return instance
