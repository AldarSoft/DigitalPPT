from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pathlib import Path


class Command(BaseCommand):
    help = "Fail when the active Django configuration is not suitable for production deployment."

    def handle(self, *args, **options):
        problems = []
        if settings.DEBUG:
            problems.append("DJANGO_DEBUG must be False.")
        if settings.SECRET_KEY == "unsafe-dev-secret-key":
            problems.append("DJANGO_SECRET_KEY must be set.")
        if len(settings.SECRET_KEY) < 50:
            problems.append("DJANGO_SECRET_KEY must contain at least 50 characters.")
        if settings.JWT_SIGNING_KEY == settings.SECRET_KEY or len(settings.JWT_SIGNING_KEY) < 64:
            problems.append("JWT_SIGNING_KEY must be separate and contain at least 64 characters.")
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
            problems.append("DB_ENGINE must be postgresql.")
        if not settings.ALLOWED_HOSTS or any(host in {"localhost", "127.0.0.1"} for host in settings.ALLOWED_HOSTS):
            problems.append("DJANGO_ALLOWED_HOSTS must contain only production hosts.")
        csrf_origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
        if not csrf_origins or any(not origin.startswith("https://") for origin in csrf_origins):
            problems.append("CSRF_TRUSTED_ORIGINS must contain production HTTPS origins.")
        if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
            problems.append("Configure a real email backend.")
        throttle_classes = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES", [])
        if "common.throttles.DatabaseScopedRateThrottle" not in throttle_classes:
            problems.append("DatabaseScopedRateThrottle must protect production API endpoints.")
        if not settings.NOTIFICATIONS_ASYNC:
            problems.append("NOTIFICATIONS_ASYNC must be enabled.")
        if settings.PAYMENTS_DEVELOPMENT_SIMULATOR:
            problems.append("PAYMENTS_DEVELOPMENT_SIMULATOR must be disabled.")
        if settings.DJANGO_ADMIN_ENABLED:
            problems.append("DJANGO_ADMIN_ENABLED must be disabled.")
        if settings.API_DOCS_ENABLED:
            problems.append("API_DOCS_ENABLED must be disabled.")
        if not getattr(settings, "CONTENT_SECURITY_POLICY", "").strip():
            problems.append("CONTENT_SECURITY_POLICY must be configured.")
        private_root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
        public_roots = {Path(settings.MEDIA_ROOT).resolve(), Path(settings.STATIC_ROOT).resolve()}
        if private_root in public_roots or any(private_root.is_relative_to(root) for root in public_roots):
            problems.append("PRIVATE_MEDIA_ROOT must be outside public media and static roots.")
        if problems:
            for problem in problems:
                self.stderr.write(self.style.ERROR(problem))
            raise CommandError("Production settings validation failed.")
        self.stdout.write(self.style.SUCCESS("Production settings validation passed."))
