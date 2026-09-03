import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import StaffMfaChallenge
from users.security import EmailVerificationService
from users.roles import StaffRole, assign_staff_roles


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
        challenge_state = StaffMfaChallenge.objects.get(user=staff)
        self.assertNotEqual(challenge_state.challenge_digest, login.data["challenge"])
        self.assertNotEqual(challenge_state.code_digest, code)
        verified = self.client.post(
            "/api/v1/users/auth/staff-mfa/",
            {"challenge": login.data["challenge"], "code": code},
            format="json",
        )
        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertTrue(verified.data["user"]["is_staff"])
        self.assertIn("access", verified.data)
        challenge_state.refresh_from_db()
        self.assertIsNotNone(challenge_state.consumed_at)
        repeated = self.client.post(
            "/api/v1/users/auth/staff-mfa/",
            {"challenge": login.data["challenge"], "code": code},
            format="json",
        )
        self.assertEqual(repeated.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_mfa_failed_attempts_persist_and_lock_the_challenge(self):
        staff = get_user_model().objects.create_user(
            username="locked-admin",
            email="locked-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            email_verified_at=timezone.now(),
        )
        login = self.client.post(
            "/api/v1/users/auth/login/",
            {"email": staff.email, "password": "StrongPass123!"},
            format="json",
        )
        issued_code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        wrong_code = "000000" if issued_code != "000000" else "000001"

        for _ in range(5):
            response = self.client.post(
                "/api/v1/users/auth/staff-mfa/",
                {"challenge": login.data["challenge"], "code": wrong_code},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        challenge_state = StaffMfaChallenge.objects.get(user=staff)
        self.assertEqual(challenge_state.attempts, 5)
        self.assertIsNone(challenge_state.consumed_at)

        locked = self.client.post(
            "/api/v1/users/auth/staff-mfa/",
            {"challenge": login.data["challenge"], "code": wrong_code},
            format="json",
        )
        self.assertEqual(locked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Too many attempts", str(locked.data))
        challenge_state.refresh_from_db()
        self.assertEqual(challenge_state.attempts, 6)
        self.assertIsNotNone(challenge_state.consumed_at)

    def test_registration_rejects_case_variant_of_existing_email(self):
        get_user_model().objects.create_user(
            username="case-owner",
            email="Case.Owner@example.com",
            password="StrongPass123!",
        )

        response = self.client.post(
            "/api/v1/users/auth/register/",
            {
                "email": "CASE.OWNER@EXAMPLE.COM",
                "first_name": "Duplicate",
                "last_name": "Identity",
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(get_user_model().objects.filter(email__iexact="case.owner@example.com").count(), 1)


class StaffAuthorizationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.super_admin = User.objects.create_user(
            username="super-admin",
            email="super-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.customer = User.objects.create_user(
            username="role-customer",
            email="role-customer@example.com",
            password="StrongPass123!",
        )
        self.user_admin = User.objects.create_user(
            username="user-admin",
            email="user-admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        assign_staff_roles(self.user_admin, [StaffRole.USER_ADMINISTRATOR])
        self.support = User.objects.create_user(
            username="support",
            email="support@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        assign_staff_roles(self.support, [StaffRole.SUPPORT])

    def test_support_role_cannot_open_user_administration(self):
        self.client.force_authenticate(self.support)
        response = self.client.get("/api/v1/users/accounts/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_administrator_can_see_customers_but_not_staff(self):
        self.client.force_authenticate(self.user_admin)
        response = self.client.get("/api/v1/users/accounts/?page_size=100")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        users = response.data if isinstance(response.data, list) else response.data["results"]
        returned_ids = {item["id"] for item in users}
        self.assertIn(self.customer.pk, returned_ids)
        self.assertNotIn(self.super_admin.pk, returned_ids)
        self.assertNotIn(self.support.pk, returned_ids)

    def test_user_administrator_cannot_promote_a_customer(self):
        self.client.force_authenticate(self.user_admin)
        response = self.client.patch(
            f"/api/v1/users/accounts/{self.customer.pk}/",
            {"is_staff": True, "staff_roles": [StaffRole.SUPPORT]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_staff)

    def test_super_administrator_staff_change_requires_current_password(self):
        self.client.force_authenticate(self.super_admin)
        missing_step_up = self.client.patch(
            f"/api/v1/users/accounts/{self.support.pk}/",
            {"first_name": "Changed"},
            format="json",
        )
        self.assertEqual(missing_step_up.status_code, status.HTTP_400_BAD_REQUEST)

        changed = self.client.patch(
            f"/api/v1/users/accounts/{self.support.pk}/",
            {"first_name": "Changed", "current_password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
