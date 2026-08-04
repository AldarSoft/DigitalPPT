from __future__ import annotations

from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from users.models import User, UserProfile
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
        )


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

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
            "date_joined",
            "profile",
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["email"],
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
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

    def create(self, validated_data):
        password = validated_data.pop("password")
        email = validated_data["email"]
        username_root = email.split("@", 1)[0]
        username = username_root
        counter = 1
        while User.objects.filter(username=username).exists():
            counter += 1
            username = f"{username_root}{counter}"
        return User.objects.create_user(
            username=username,
            password=password,
            is_customer=True,
            **validated_data,
        )


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
    profile = UserProfileSerializer(required=False)
    phone_number = serializers.CharField(required=False, allow_blank=True, validators=[validate_phone])

    class Meta:
        model = User
        fields = (
            "email",
            "username",
            "password",
            "first_name",
            "last_name",
            "phone_number",
            "is_customer",
            "is_staff",
            "is_active",
            "profile",
        )

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", None)
        user = User.objects.create_user(password=password, **validated_data)
        if profile_data:
            for field, value in profile_data.items():
                setattr(user.profile, field, value)
            user.profile.save()
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()

        if profile_data is not None:
            profile = instance.profile
            for field, value in profile_data.items():
                setattr(profile, field, value)
            profile.save()

        return instance
