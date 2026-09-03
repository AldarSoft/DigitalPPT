from .base import *  # noqa: F403,F401

DEBUG = True
DJANGO_ADMIN_ENABLED = True

# Keep browser-to-API traffic visible while developing locally.
MIDDLEWARE += ["common.request_logging.DevelopmentRequestLoggingMiddleware"]  # noqa: F405

# Development exposes the customer payment flow through a non-charging
# simulator. Production explicitly disables the simulator in prod.py.
PAYMENTS_STOREFRONT_ENABLED = env("PAYMENTS_STOREFRONT_ENABLED", default=True, cast=bool)  # noqa: F405
PAYMENTS_DEVELOPMENT_SIMULATOR = env("PAYMENTS_DEVELOPMENT_SIMULATOR", default=True, cast=bool)  # noqa: F405

CORS_ALLOWED_ORIGINS = list(globals().get("CORS_ALLOWED_ORIGINS", []))
CSRF_TRUSTED_ORIGINS = list(globals().get("CSRF_TRUSTED_ORIGINS", []))

for origin in ("http://127.0.0.1:5173", "http://127.0.0.1:4173"):
    if origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(origin)
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)
