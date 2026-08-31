"""Validate production security settings before starting a deployment process."""

import os
import secrets
import sys


def validate_configuration():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    import django
    from django.core.cache import cache
    from django.core.management import call_command

    django.setup()
    call_command("check", deploy=True, fail_level="ERROR")
    call_command("check_production_settings")
    cache_key = f"deployment:security-check:{secrets.token_urlsafe(12)}"
    cache.set(cache_key, "ok", timeout=30)
    if cache.get(cache_key) != "ok":
        raise SystemExit("Shared Redis cache validation failed.")
    cache.delete(cache_key)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"web", "worker"}:
        raise SystemExit("Usage: python deploy_start.py [web|worker]")

    validate_configuration()
    if sys.argv[1] == "web":
        port = os.environ.get("PORT", "8000")
        command = [
            "gunicorn",
            "config.wsgi:application",
            "--bind",
            f"0.0.0.0:{port}",
            "--workers",
            os.environ.get("WEB_CONCURRENCY", "3"),
            "--timeout",
            "60",
        ]
    else:
        command = [sys.executable, "manage.py", "process_notifications"]
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
