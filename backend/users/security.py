import hashlib
import hmac
import logging
import secrets

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from rest_framework.exceptions import ValidationError

from common.email_delivery import send_application_email
from users.models import User


logger = logging.getLogger("security.authentication")


class EmailVerificationService:
    salt = "users.email-verification.v1"

    @classmethod
    def token_for(cls, user):
        return signing.dumps(
            {"user_id": user.pk, "email": user.email},
            salt=cls.salt,
            compress=True,
        )

    @classmethod
    def send(cls, user):
        token = cls.token_for(user)
        verification_url = (
            f"{settings.FRONTEND_URL.rstrip('/')}/auth/verify-email?token={token}"
        )
        send_application_email(
            subject="Verify your Digital PTT email",
            text_body=(
                f"Hello {user.get_full_name() or user.email},\n\n"
                "Verify your email address to finish creating your Digital PTT account:\n"
                f"{verification_url}\n\n"
                "This link expires in 24 hours. If you did not create this account, "
                "you can ignore this message."
            ),
            recipients=[user.email],
        )
        return verification_url

    @classmethod
    def send_safely(cls, user):
        try:
            return cls.send(user)
        except Exception:
            logger.exception("Email verification delivery failed for user_id=%s", user.pk)
            return ""

    @classmethod
    @transaction.atomic
    def verify(cls, token):
        try:
            payload = signing.loads(
                token,
                salt=cls.salt,
                max_age=settings.EMAIL_VERIFICATION_TIMEOUT,
            )
        except signing.SignatureExpired as exc:
            raise ValidationError({"token": "This verification link has expired."}) from exc
        except signing.BadSignature as exc:
            raise ValidationError({"token": "This verification link is invalid."}) from exc

        user = User.objects.select_for_update().filter(
            pk=payload.get("user_id"),
            email__iexact=payload.get("email", ""),
            is_active=True,
        ).first()
        if not user:
            raise ValidationError({"token": "This verification link is invalid."})
        if user.is_email_verified:
            raise ValidationError({"token": "This verification link has already been used."})
        user.mark_email_verified()
        logger.info("Email verified for user_id=%s", user.pk)
        return user


class StaffMfaService:
    key_prefix = "users:staff-mfa:"

    @staticmethod
    def _digest(challenge, code):
        value = f"{settings.SECRET_KEY}:{challenge}:{code}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    @classmethod
    def begin(cls, user):
        challenge = secrets.token_urlsafe(32)
        code = f"{secrets.randbelow(1_000_000):06d}"
        cache.set(
            f"{cls.key_prefix}{challenge}",
            {"user_id": user.pk, "digest": cls._digest(challenge, code), "attempts": 0},
            timeout=settings.STAFF_MFA_TIMEOUT,
        )
        send_application_email(
            subject="Your Digital PTT administrator sign-in code",
            text_body=(
                f"Hello {user.get_full_name() or user.email},\n\n"
                f"Your administrator sign-in code is: {code}\n\n"
                "It expires in 10 minutes. If you did not attempt to sign in, reset "
                "your password and contact another administrator."
            ),
            recipients=[user.email],
        )
        logger.info("Staff MFA challenge issued for user_id=%s", user.pk)
        return challenge

    @classmethod
    def verify(cls, challenge, code):
        key = f"{cls.key_prefix}{challenge}"
        state = cache.get(key)
        if not state:
            raise ValidationError({"code": "This sign-in code is invalid or expired."})

        state["attempts"] = int(state.get("attempts", 0)) + 1
        if state["attempts"] > 5:
            cache.delete(key)
            raise ValidationError({"code": "Too many attempts. Sign in again for a new code."})

        expected = state.get("digest", "")
        supplied = cls._digest(challenge, code.strip())
        if not hmac.compare_digest(expected, supplied):
            cache.set(key, state, timeout=settings.STAFF_MFA_TIMEOUT)
            logger.warning("Invalid staff MFA code for user_id=%s", state.get("user_id"))
            raise ValidationError({"code": "This sign-in code is invalid or expired."})

        user = User.objects.filter(pk=state.get("user_id"), is_active=True, is_staff=True).first()
        cache.delete(key)
        if not user:
            raise ValidationError({"code": "This sign-in code is invalid or expired."})
        logger.info("Staff MFA completed for user_id=%s", user.pk)
        return user
