"""Deterministic test settings that may reuse the configured database engine."""

import tempfile

from .dev import *  # noqa: F403,F401

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MICROSOFT_GRAPH_EMAIL_ENABLED = False
POWER_AUTOMATE_ENABLED = False
NOTIFICATIONS_ASYNC = False

AUTH_REFRESH_COOKIE_SECURE = False
PAYMENTS_STOREFRONT_ENABLED = True
PAYMENTS_DEVELOPMENT_SIMULATOR = True

_test_media_root = tempfile.mkdtemp(prefix="digitalptt-test-media-")
MEDIA_ROOT = _test_media_root
PRIVATE_MEDIA_ROOT = tempfile.mkdtemp(prefix="digitalptt-test-private-media-")
