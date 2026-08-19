from __future__ import annotations

from pathlib import Path
from datetime import timedelta

from common.env import env, load_env_file

BASE_DIR = Path(__file__).resolve().parents[2]
load_env_file(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-dev-secret-key")
DEBUG = env("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=list)
SITE_NAME = env("SITE_NAME", default="Digital PTT")

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "users",
    "products",
    "orders",
    "quotes",
    "payments",
    "licensing",
    "core",
    'drf_spectacular',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DB_ENGINE = env("DB_ENGINE", default="sqlite").strip().lower()

if DB_ENGINE == "postgresql":
    postgres_options = {}
    postgres_sslmode = env("POSTGRES_SSLMODE", default="").strip()
    if postgres_sslmode:
        postgres_options["sslmode"] = postgres_sslmode

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="rack_and_bracket"),
            "USER": env("POSTGRES_USER", default="rack_and_bracket"),
            "PASSWORD": env("POSTGRES_PASSWORD", default=""),
            "HOST": env("POSTGRES_HOST", default="127.0.0.1"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": env("POSTGRES_CONN_MAX_AGE", default=60, cast=int),
            "OPTIONS": postgres_options,
        }
    }
elif DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / env("SQLITE_NAME", default="commerce.sqlite3"),
        }
    }
else:
    raise RuntimeError("DB_ENGINE must be either 'sqlite' or 'postgresql'.")

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "PAGE_SIZE": env("API_PAGE_SIZE", default=20, cast=int),
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("THROTTLE_AUTH", default="10/min"),
        "token_refresh": env("THROTTLE_TOKEN_REFRESH", default="30/min"),
        "contact": env("THROTTLE_CONTACT", default="5/hour"),
        "quote": env("THROTTLE_QUOTE", default="10/hour"),
        "checkout": env("THROTTLE_CHECKOUT", default="20/hour"),
        "image_upload": env("THROTTLE_IMAGE_UPLOAD", default="30/hour"),
        "payment_test": env("THROTTLE_PAYMENT_TEST", default="30/hour"),
    },
    "COERCE_DECIMAL_TO_STRING": False,
}

PAYMENTS_STOREFRONT_ENABLED = env("PAYMENTS_STOREFRONT_ENABLED", default=False, cast=bool)
PAYMENTS_DEVELOPMENT_SIMULATOR = env("PAYMENTS_DEVELOPMENT_SIMULATOR", default=False, cast=bool)
PAYMENT_SESSION_TTL_MINUTES = env("PAYMENT_SESSION_TTL_MINUTES", default=30, cast=int)
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID", default="")
PAYPAL_CLIENT_SECRET = env("PAYPAL_CLIENT_SECRET", default="")
PAYPAL_WEBHOOK_ID = env("PAYPAL_WEBHOOK_ID", default="")
QPAY_CLIENT_ID = env("QPAY_CLIENT_ID", default="")
QPAY_CLIENT_SECRET = env("QPAY_CLIENT_SECRET", default="")
QPAY_INVOICE_CODE = env("QPAY_INVOICE_CODE", default="")
PAYMENT_BANK_TRANSFER_INSTRUCTIONS = env("PAYMENT_BANK_TRANSFER_INSTRUCTIONS", default="")

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

CORS_ALLOWED_ORIGINS = env(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:5173",
    cast=list,
)

CORS_ALLOW_CREDENTIALS = True

AUTH_REFRESH_COOKIE_NAME = env("AUTH_REFRESH_COOKIE_NAME", default="digital_ptt_refresh")
AUTH_REFRESH_COOKIE_SECURE = env(
    "AUTH_REFRESH_COOKIE_SECURE",
    default=not DEBUG,
    cast=bool,
)
AUTH_REFRESH_COOKIE_SAMESITE = env("AUTH_REFRESH_COOKIE_SAMESITE", default="Strict")
AUTH_REFRESH_COOKIE_DOMAIN = env("AUTH_REFRESH_COOKIE_DOMAIN", default="") or None
AUTH_REFRESH_COOKIE_PATH = "/api/v1/users/auth/"

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="sales@digitalptt.local")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_USE_SSL = env("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_TIMEOUT = env("EMAIL_TIMEOUT", default=10, cast=int)
QUOTE_NOTIFICATION_EMAIL = env("QUOTE_NOTIFICATION_EMAIL", default="")

MICROSOFT_GRAPH_EMAIL_ENABLED = env(
    "MICROSOFT_GRAPH_EMAIL_ENABLED", default=False, cast=bool
)
MICROSOFT_GRAPH_TENANT_ID = env("MICROSOFT_GRAPH_TENANT_ID", default="")
MICROSOFT_GRAPH_CLIENT_ID = env("MICROSOFT_GRAPH_CLIENT_ID", default="")
MICROSOFT_GRAPH_CLIENT_SECRET = env("MICROSOFT_GRAPH_CLIENT_SECRET", default="")
MICROSOFT_GRAPH_SENDER_EMAIL = env("MICROSOFT_GRAPH_SENDER_EMAIL", default="")
MICROSOFT_GRAPH_TIMEOUT = env("MICROSOFT_GRAPH_TIMEOUT", default=30, cast=int)

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise RuntimeError("Enable only one of EMAIL_USE_TLS or EMAIL_USE_SSL.")

POWER_AUTOMATE_ENABLED = env("POWER_AUTOMATE_ENABLED", default=False, cast=bool)
POWER_AUTOMATE_WEBHOOK_URL = env("POWER_AUTOMATE_WEBHOOK_URL", default="")
POWER_AUTOMATE_TIMEOUT = env("POWER_AUTOMATE_TIMEOUT", default=10, cast=int)
POWER_AUTOMATE_SHARED_SECRET = env("POWER_AUTOMATE_SHARED_SECRET", default="")

NOTIFICATIONS_ASYNC = env("NOTIFICATIONS_ASYNC", default=False, cast=bool)
NOTIFICATION_MAX_ATTEMPTS = env("NOTIFICATION_MAX_ATTEMPTS", default=5, cast=int)
NOTIFICATION_RETRY_SECONDS = env("NOTIFICATION_RETRY_SECONDS", default=60, cast=int)

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")
PASSWORD_RESET_TIMEOUT = env("PASSWORD_RESET_TIMEOUT", default=3600, cast=int)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(levelname)s %(asctime)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "django.log",
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": env("LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django.db.backends": {
            "handlers": ["console"],
            "level": env("DJANGO_DB_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
    },
}

CACHE_TTL_SECONDS = env("CACHE_TTL_SECONDS", default=300, cast=int)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "commerce-platform-cache",
        "TIMEOUT": CACHE_TTL_SECONDS,
    }
}

SPECTACULAR_SETTINGS = {
    "TITLE": f"{SITE_NAME} API",
    "DESCRIPTION": (
        f"Online store API for {SITE_NAME} products, categories, customer accounts, "
        "orders, quotes, promotions, site content, and administration."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "POSTPROCESSING_HOOKS": [
        "config.schema.categorize_operations",
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
    "TAGS": [
        {
            "name": "Authentication",
            "description": (
                "Login, registration, session refresh, and password recovery."
            ),
        },
        {
            "name": "User Administration",
            "description": "Staff management of customer and administrator accounts.",
        },
        {
            "name": "Product Catalog",
            "description": (
                "Products, categories, inventory-facing catalog data, and "
                "product media."
            ),
        },
        {
            "name": "Checkout",
            "description": "Cart checkout and order creation.",
        },
        {
            "name": "Orders",
            "description": "Customer and staff order workflows.",
        },
        {
            "name": "Quotes",
            "description": (
                "Quote requests, review, pricing, messages, and invoicing."
            ),
        },
        {
            "name": "Payments",
            "description": (
                "Payment providers, checkout sessions, attempts, and payment "
                "status."
            ),
        },
        {
            "name": "Licensing",
            "description": (
                "Organization licenses, capacity, allocations, teams, and "
                "invitations."
            ),
        },
        {
            "name": "Notifications",
            "description": "Customer status and account notifications.",
        },
        {
            "name": "Support",
            "description": "Customer contact and support requests.",
        },
        {
            "name": "Site Content",
            "description": "Storefront settings, banners, and promotions.",
        },
        {
            "name": "Other",
            "description": "API operations not yet assigned to a domain.",
        },
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "displayOperationId": False,
        "displayRequestDuration": True,
        "docExpansion": "none",
        "filter": True,
        "operationsSorter": "method",
        "persistAuthorization": True,
        "tagsSorter": "alpha",
        "defaultModelsExpandDepth": 1,
    },
    "ENUM_NAME_OVERRIDES": {
        "ProductStatusEnum": "products.models.Product.Status",
        "OrderStatusEnum": "orders.models.Order.Status",
        "QuoteStatusEnum": "quotes.models.QuoteRequest.Status",
    },
}
