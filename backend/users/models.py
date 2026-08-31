from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class UserManager(DjangoUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The email address must be set.")
        username = extra_fields.pop("username", None)
        if not username:
            raise ValueError("The username must be set.")

        email = self.normalize_email(email)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        # Internal account creation is trusted. Public registration explicitly
        # passes None and must complete the verification-email flow.
        extra_fields.setdefault("email_verified_at", timezone.now())
        return super().create_user(
            username=username,
            email=email,
            password=password,
            **extra_fields,
        )

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_customer", False)
        extra_fields.setdefault("email_verified_at", timezone.now())

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password=password, **extra_fields)


class User(TimeStampedModel, AbstractUser):
    email = models.EmailField(unique=True, db_index=True)
    phone_number = models.CharField(max_length=32, blank=True)
    is_customer = models.BooleanField(default=True, db_index=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["email", "is_active"]),
            models.Index(fields=["is_customer", "is_active"]),
        ]

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def is_email_verified(self):
        return self.email_verified_at is not None

    def mark_email_verified(self):
        if self.email_verified_at is None:
            self.email_verified_at = timezone.now()
            self.save(update_fields=["email_verified_at", "updated_at"])


class UserProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    company_name = models.CharField(max_length=255, blank=True)
    job_title = models.CharField(max_length=255, blank=True)
    avatar_url = models.CharField(max_length=500, blank=True)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    use_different_shipping_address = models.BooleanField(default=False)
    shipping_address_line_1 = models.CharField(max_length=255, blank=True)
    shipping_address_line_2 = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=120, blank=True)
    shipping_state = models.CharField(max_length=120, blank=True)
    shipping_country = models.CharField(max_length=120, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        indexes = [
            models.Index(fields=["country", "city"]),
        ]

    def __str__(self):
        return f"Profile for {self.user.email}"
