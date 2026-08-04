"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

current_settings = os.environ.get("DJANGO_SETTINGS_MODULE")
if not current_settings or current_settings == "config.settings":
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"

application = get_wsgi_application()
