from .base import *  # noqa: F403,F401

DEBUG = False
PAYMENTS_DEVELOPMENT_SIMULATOR = False

if SECRET_KEY == "unsafe-dev-secret-key":  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set for production.")

CONTENT_SECURITY_POLICY = env(  # noqa: F405
    "CONTENT_SECURITY_POLICY",
    default=(
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; img-src 'self' data: https:; "
        "font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self'"
    ),
)
MIDDLEWARE.insert(1, "common.security_headers.SecurityHeadersMiddleware")  # noqa: F405

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = env("SECURE_HSTS_SECONDS", default=31536000, cast=int)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
]

# Production logs are structured for collection by the hosting platform.
LOGGING["handlers"]["console"]["formatter"] = "json"  # noqa: F405
LOGGING["root"]["handlers"] = ["console"]  # noqa: F405
