from django.urls import include, path
from rest_framework.routers import DefaultRouter

from users.views import AuthViewSet, CookieTokenRefreshView, UserAdminViewSet

router = DefaultRouter()
router.register("accounts", UserAdminViewSet, basename="user-account")

urlpatterns = [
    path("auth/login/", AuthViewSet.as_view({"post": "login"}), name="auth-login"),
    path("auth/register/", AuthViewSet.as_view({"post": "register"}), name="auth-register"),
    path("auth/verify-email/", AuthViewSet.as_view({"post": "verify_email"}), name="auth-verify-email"),
    path("auth/resend-verification/", AuthViewSet.as_view({"post": "resend_verification"}), name="auth-resend-verification"),
    path("auth/staff-mfa/", AuthViewSet.as_view({"post": "verify_staff_mfa"}), name="auth-staff-mfa"),
    path(
        "auth/password-reset/",
        AuthViewSet.as_view({"post": "password_reset_request"}),
        name="auth-password-reset",
    ),
    path(
        "auth/password-reset/confirm/",
        AuthViewSet.as_view({"post": "password_reset_confirm"}),
        name="auth-password-reset-confirm",
    ),
    path("auth/logout/", AuthViewSet.as_view({"post": "logout"}), name="auth-logout"),
    path("auth/me/", AuthViewSet.as_view({"get": "me", "patch": "me"}), name="auth-me"),
    path("auth/refresh/", CookieTokenRefreshView.as_view(), name="auth-refresh"),
    path("", include(router.urls)),
]
