from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Fail when the active Django configuration is not suitable for production deployment."

    def handle(self, *args, **options):
        problems = []
        if settings.DEBUG:
            problems.append("DJANGO_DEBUG must be False.")
        if settings.SECRET_KEY == "unsafe-dev-secret-key":
            problems.append("DJANGO_SECRET_KEY must be set.")
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
            problems.append("DB_ENGINE must be postgresql.")
        if not settings.ALLOWED_HOSTS or any(host in {"localhost", "127.0.0.1"} for host in settings.ALLOWED_HOSTS):
            problems.append("DJANGO_ALLOWED_HOSTS must contain only production hosts.")
        csrf_origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
        if not csrf_origins or any(not origin.startswith("https://") for origin in csrf_origins):
            problems.append("CSRF_TRUSTED_ORIGINS must contain production HTTPS origins.")
        if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
            problems.append("Configure a real email backend.")
        if not settings.NOTIFICATIONS_ASYNC:
            problems.append("NOTIFICATIONS_ASYNC must be enabled.")
        if settings.PAYMENTS_DEVELOPMENT_SIMULATOR:
            problems.append("PAYMENTS_DEVELOPMENT_SIMULATOR must be disabled.")
        if problems:
            for problem in problems:
                self.stderr.write(self.style.ERROR(problem))
            raise CommandError("Production settings validation failed.")
        self.stdout.write(self.style.SUCCESS("Production settings validation passed."))
