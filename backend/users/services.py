import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from common.email_delivery import send_application_email


logger = logging.getLogger(__name__)


class AccountSetupService:
    @staticmethod
    def _username(email):
        User = get_user_model()
        root = email.split("@", 1)[0][:120] or "client"
        candidate = root
        counter = 1
        while User.objects.filter(username=candidate).exists():
            counter += 1
            candidate = f"{root[:110]}-{counter}"
        return candidate

    @staticmethod
    def setup_url(user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return (
            f"{settings.FRONTEND_URL.rstrip('/')}/auth/reset-password"
            f"?uid={uid}&token={token}&setup=1"
        )

    @classmethod
    def send_setup_email(cls, user):
        setup_url = cls.setup_url(user)
        try:
            send_application_email(
                subject="Set up your Digital PTT account",
                text_body=(
                    f"Hello {user.get_full_name() or user.email},\n\n"
                    "An administrator created a Digital PTT account for you. "
                    "Use this single-use link to choose your password:\n"
                    f"{setup_url}\n\n"
                    "If you were not expecting this account, contact Digital PTT support."
                ),
                recipients=[user.email],
            )
        except Exception:
            logger.exception("Could not send account setup email for user %s", user.pk)
        return setup_url

    @classmethod
    def create_user(cls, *, email, first_name="", last_name="", phone_number=""):
        User = get_user_model()
        normalized = User.objects.normalize_email(email).strip().casefold()
        if User.objects.filter(email__iexact=normalized).exists():
            raise ValidationError({"email": "An account already uses this email address."})
        user = User.objects.create_user(
            email=normalized,
            username=cls._username(normalized),
            password=None,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone_number=phone_number.strip(),
            is_customer=True,
        )
        user.set_unusable_password()
        user.save(update_fields=["password", "updated_at"])
        transaction.on_commit(lambda: cls.send_setup_email(user))
        return user
