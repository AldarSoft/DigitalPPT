import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from users.security import EmailVerificationService


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MICROSOFT_GRAPH_EMAIL_ENABLED=False,
)
class AuthenticationSecurityTests(APITestCase):
    def test_registration_requires_email_verification_before_tokens_are_issued(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/users/auth/register/",
                {
                    "email": "new-customer@example.com",
                    "first_name": "New",
                    "last_name": "Customer",
                    "password": "StrongPass123!",
                    "confirm_password": "StrongPass123!",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("access", response.data)
        user = get_user_model().objects.get(email="new-customer@example.com")
        self.assertIsNone(user.email_verified_at)
        self.assertEqual(len(mail.outbox), 1)

        login = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": user.email, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_verification_is_single_use_and_starts_customer_session(self):
        user = get_user_model().objects.create_user(
            username="verify-customer",
            email="verify-customer@example.com",
            password="StrongPass123!",
            email_verified_at=None,
        )
        token = EmailVerificationService.token_for(user)

        response = self.client.post(
            "/api/v1/users/auth/verify-email/",
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        from django.conf import settings
        self.assertIn(settings.AUTH_REFRESH_COOKIE_NAME, response.cookies)
        user.refresh_from_db()
        self.assertIsNotNone(user.email_verified_at)
        repeated = self.client.post(
            "/api/v1/users/auth/verify-email/",
            {"token": token},
            format="json",
        )
        self.assertEqual(repeated.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_password_login_requires_email_mfa_before_tokens(self):
        staff = get_user_model().objects.create_user(
            username="secure-admin",
            email="secure-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            email_verified_at=timezone.now(),
        )

        login = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": staff.email, "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(login.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(login.data["mfa_required"])
        self.assertNotIn("access", login.data)
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        verified = self.client.post(
            "/api/v1/users/auth/staff-mfa/",
            {"challenge": login.data["challenge"], "code": code},
            format="json",
        )
        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertTrue(verified.data["user"]["is_staff"])
        self.assertIn("access", verified.data)
