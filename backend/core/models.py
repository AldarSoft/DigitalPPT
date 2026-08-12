from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import ActiveModel, TimeStampedModel


class Banner(ActiveModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    cta_label = models.CharField(max_length=120, blank=True)
    cta_url = models.CharField(max_length=500, blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Banner"
        verbose_name_plural = "Banners"
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def __str__(self):
        return self.title


def default_homepage_hero_stats():
    return [
        {"value": "34+", "label": "field products"},
        {"value": "4", "label": "radio categories"},
        {"value": "IP68", "label": "ready options"},
    ]


def default_homepage_solution_benefits():
    return [
        "Live GPS visibility between Android radios",
        "Authorized team location sharing",
        "Nationwide POC coverage",
        "Android + analog dual-mode options",
    ]


def default_homepage_comparison_products():
    return [
        {"model": "IPTT510", "best_for": "Everyday teams", "network": "4G LTE POC", "system": "Dedicated radio", "protection": "Field-ready", "price": "$120"},
        {"model": "IPTT81", "best_for": "Hybrid fleets", "network": "POC + Analog", "system": "Android / dual SIM", "protection": "IP68 waterproof", "price": "$340"},
        {"model": "IPTT760", "best_for": "Hazardous sites", "network": "4G LTE POC", "system": "ATEX-rated", "protection": "Industrial safety", "price": "Contact us"},
    ]


def default_homepage_resources():
    return [
        {"eyebrow": "VHF VS UHF", "title": "What is VHF radio, and how is it different from UHF?", "description": "A practical guide to range, terrain and choosing the right band.", "image_url": "/images/article-dish.png", "url": ""},
        {"eyebrow": "BUYER'S GUIDE", "title": "How to choose the right two-way radio for your needs", "description": "Match network, durability and audio to the way your team works.", "image_url": "/images/article-guide.png", "url": ""},
        {"eyebrow": "FLEET GUIDE", "title": "How GPS-enabled POC radios improve fleet visibility", "description": "See how connected teams combine instant voice with live location awareness.", "image_url": "/images/article-audio.png", "url": ""},
    ]


class SiteSetting(TimeStampedModel):
    site_name = models.CharField(max_length=255, default="Digital PTT")
    tagline = models.CharField(max_length=255, blank=True)
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=32, blank=True)
    company_address = models.TextField(blank=True)
    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    commerce_defaults_enabled = models.BooleanField(default=False)
    default_currency = models.CharField(max_length=10, default="USD")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    flat_shipping_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    free_shipping_minimum = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    working_hours = models.CharField(max_length=255, blank=True)
    about_story = models.TextField(blank=True)
    about_mission = models.TextField(blank=True)
    about_vision = models.TextField(blank=True)
    about_image_url = models.CharField(max_length=500, blank=True)
    about_team = models.JSONField(default=list, blank=True)
    about_values = models.JSONField(default=list, blank=True)
    about_stats = models.JSONField(default=list, blank=True)
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    homepage_hero_secondary_cta_label = models.CharField(max_length=120, default="Talk to an expert")
    homepage_hero_secondary_cta_url = models.CharField(max_length=500, default="#contact")
    homepage_hero_stats = models.JSONField(default=default_homepage_hero_stats, blank=True)
    homepage_solution_eyebrow = models.CharField(max_length=255, default="ANDROID GPS FLEET VISIBILITY")
    homepage_solution_title = models.CharField(max_length=255, default="Push-to-talk with live team location")
    homepage_solution_description = models.TextField(default="GPS-enabled Android radios let authorized users see one another's live locations directly on their devices. Crews can talk, check positions and coordinate across 4G LTE without returning to dispatch.")
    homepage_solution_benefits = models.JSONField(default=default_homepage_solution_benefits, blank=True)
    homepage_comparison_eyebrow = models.CharField(max_length=255, default="CHOOSE WITH CONFIDENCE")
    homepage_comparison_title = models.CharField(max_length=255, default="The right radio for every role")
    homepage_comparison_products = models.JSONField(default=default_homepage_comparison_products, blank=True)
    homepage_resources_eyebrow = models.CharField(max_length=255, default="KNOWLEDGE BASE")
    homepage_resources_title = models.CharField(max_length=255, default="Better communication starts here")
    homepage_resources = models.JSONField(default=default_homepage_resources, blank=True)
    homepage_contact_eyebrow = models.CharField(max_length=255, default="NOT SURE WHERE TO START?")
    homepage_contact_title = models.CharField(max_length=255, default="Tell us how your team works. We'll match the right system.")
    homepage_contact_description = models.TextField(default="From a single radio to a connected fleet, get practical guidance before you buy.")
    homepage_contact_cta_label = models.CharField(max_length=120, default="Contact a specialist")
    homepage_contact_cta_url = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "Site Setting"
        verbose_name_plural = "Site Settings"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.pk = SiteSetting.objects.values_list("pk", flat=True).first() or 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        return cls.objects.order_by("pk").first() or cls.objects.create()

    def __str__(self):
        return self.site_name


class ContactMessage(TimeStampedModel):
    name = models.CharField(max_length=255)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    subject = models.CharField(max_length=120)
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["is_read", "created_at"])]

    def __str__(self):
        return f"{self.name} - {self.subject}"


class Promotion(ActiveModel):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed amount"

    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
    )
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    times_redeemed = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.title}"


class NotificationJob(TimeStampedModel):
    class Kind(models.TextChoices):
        QUOTE_CUSTOMER_EMAIL = "quote_customer_email", "Quote customer email"
        QUOTE_STAFF_EMAIL = "quote_staff_email", "Quote staff email"
        QUOTE_WEBHOOK = "quote_webhook", "Quote Power Automate webhook"
        QUOTE_READY_EMAIL = "quote_ready_email", "Quote ready email"
        QUOTE_MESSAGE_EMAIL = "quote_message_email", "Quote message email"
        ORDER_STATUS_EMAIL = "order_status_email", "Order status email"
        ORDER_STATUS_WEBHOOK = "order_status_webhook", "Order status webhook"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=40, choices=Kind.choices, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ("available_at", "id")
        indexes = [
            models.Index(
                fields=["status", "available_at"],
                name="core_notifi_status_2f9d7b_idx",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} ({self.status})"


class UserNotification(TimeStampedModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=500)
    is_read = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=["recipient", "is_read", "created_at"],
                name="core_adminn_recipient_idx",
            )
        ]

    def __str__(self):
        return f"{self.recipient} - {self.title}"
