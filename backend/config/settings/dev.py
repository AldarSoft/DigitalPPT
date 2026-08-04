from .base import *  # noqa: F403,F401

DEBUG = True

CORS_ALLOWED_ORIGINS = list(globals().get("CORS_ALLOWED_ORIGINS", []))
CSRF_TRUSTED_ORIGINS = list(globals().get("CSRF_TRUSTED_ORIGINS", []))

for origin in ("http://127.0.0.1:5173", "http://127.0.0.1:4173"):
    if origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(origin)
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)
