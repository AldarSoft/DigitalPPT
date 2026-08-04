from __future__ import annotations

import json
import logging
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_power_automate_event(event_name: str, data: dict) -> bool:
    """Post a business event to an optional Power Automate HTTP-trigger flow."""
    if not settings.POWER_AUTOMATE_ENABLED:
        return False

    webhook_url = settings.POWER_AUTOMATE_WEBHOOK_URL.strip()
    if not webhook_url:
        logger.warning("Power Automate is enabled but no webhook URL is configured.")
        return False

    parsed_url = urlparse(webhook_url)
    if parsed_url.scheme != "https" and not settings.DEBUG:
        logger.error("Power Automate webhook must use HTTPS outside development.")
        return False

    payload = {
        "event": event_name,
        "source": "rack-and-bracket",
        "sent_at": timezone.now().isoformat(),
        "data": data,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "rack-and-bracket-backend/1.0",
    }
    if settings.POWER_AUTOMATE_SHARED_SECRET:
        headers["X-Webhook-Secret"] = settings.POWER_AUTOMATE_SHARED_SECRET

    request = Request(
        webhook_url,
        data=json.dumps(payload, default=str).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.POWER_AUTOMATE_TIMEOUT) as response:
            status_code = response.getcode()
            if 200 <= status_code < 300:
                return True
            logger.error("Power Automate returned HTTP %s for %s.", status_code, event_name)
    except Exception:
        logger.exception("Could not deliver Power Automate event %s.", event_name)

    return False
