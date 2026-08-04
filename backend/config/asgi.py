"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

current_settings = os.environ.get("DJANGO_SETTINGS_MODULE")
if not current_settings or current_settings == "config.settings":
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"

application = get_asgi_application()
