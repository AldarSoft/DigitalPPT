import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from common.email_delivery import send_application_email
from users.models import User
from users.serializers import (
    AdminUserWriteSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    RegistrationSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)

def set_refresh_cookie(response, refresh_value):
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        refresh_value,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def build_auth_response(user):
    refresh = RefreshToken.for_user(user)
    return (
        {
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
        },
        str(refresh),
    )


class CookieTokenRefreshView(TokenRefreshView):
    throttle_scope = "token_refresh"

    def post(self, request, *args, **kwargs):
        refresh_value = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not refresh_value:
            return Response(
                {"detail": "Refresh session is missing."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            refresh_token = RefreshToken(refresh_value)
            JWTAuthentication().get_user(refresh_token)
            serializer = self.get_serializer(data={"refresh": refresh_value})
            serializer.is_valid(raise_exception=True)
        except (AuthenticationFailed, TokenError, User.DoesNotExist):
            response = Response(
                {"detail": "Refresh session is no longer valid."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_refresh_cookie(response)
            return response
        response_data = dict(serializer.validated_data)
        rotated_refresh = response_data.pop("refresh", refresh_value)
        response = Response(response_data)
        set_refresh_cookie(response, rotated_refresh)
        return response

class AuthViewSet(viewsets.GenericViewSet):
    queryset = User.objects.select_related("profile").all()

    def get_permissions(self):
        if self.action in {
            "login",
            "register",
            "password_reset_request",
            "password_reset_confirm",
        }:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_throttles(self):
        self.throttle_scope = (
            "auth"
            if self.action in {
                "login",
                "register",
                "password_reset_request",
                "password_reset_confirm",
            }
            else None
        )
        return super().get_throttles()

    def get_serializer_class(self):
        if self.action == "login":
            return LoginSerializer
        if self.action == "register":
            return RegistrationSerializer
        if self.action == "password_reset_request":
            return PasswordResetRequestSerializer
        if self.action == "password_reset_confirm":
            return PasswordResetConfirmSerializer
        if self.action == "me" and self.request.method == "PATCH":
            return ProfileUpdateSerializer
        return UserSerializer

    @action(detail=False, methods=["post"])
    def login(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        response_data, refresh_value = build_auth_response(user)
        response = Response(response_data)
        set_refresh_cookie(response, refresh_value)
        return response

    @action(detail=False, methods=["post"])
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response_data, refresh_value = build_auth_response(user)
        response = Response(response_data, status=status.HTTP_201_CREATED)
        set_refresh_cookie(response, refresh_value)
        return response

    @action(detail=False, methods=["post"])
    def password_reset_request(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = (
                f"{settings.FRONTEND_URL.rstrip('/')}/auth/reset-password"
                f"?uid={uid}&token={token}"
            )
            try:
                send_application_email(
                    subject="Reset your Digital PTT password",
                    text_body=(
                        f"Hello {user.get_full_name() or user.email},\n\n"
                        "Use the link below to set a new password:\n"
                        f"{reset_url}\n\n"
                        "This link expires in one hour and can only be used once. "
                        "If you did not request this, you can ignore this email."
                    ),
                    recipients=[user.email],
                )
            except Exception:
                logger.exception("Could not send password reset email for user %s", user.pk)

        return Response(
            {"detail": "If an active account uses that email, a reset link has been sent."}
        )

    @action(detail=False, methods=["post"])
    def password_reset_confirm(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response = Response({"detail": "Your password has been reset. You can now sign in."})
        clear_refresh_cookie(response)
        return response

    @action(detail=False, methods=["post"])
    def logout(self, request):
        refresh_value = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if refresh_value:
            try:
                RefreshToken(refresh_value).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response

    @action(detail=False, methods=["get", "patch"])
    def me(self, request):
        if request.method == "GET":
            return Response(UserSerializer(request.user).data)

        serializer = self.get_serializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data)


class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("profile").all()
    permission_classes = [IsAdminUser]
    search_fields = ("email", "username", "first_name", "last_name")
    ordering_fields = ("created_at", "email", "last_name")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return AdminUserWriteSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response_data = UserSerializer(user).data
        response_data["account_setup_email_queued"] = bool(
            getattr(user, "_account_setup_email_queued", False)
        )
        headers = self.get_success_headers(response_data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)
