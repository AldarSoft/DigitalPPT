"""Validate production security settings before starting a deployment process."""

import os
import sys


def validate_configuration():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    import django
    from django.core.management import call_command
    from django.db import connection

    django.setup()
    call_command("check", deploy=True, fail_level="ERROR")
    call_command("check_production_settings")
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise SystemExit("Primary database validation failed.")


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
