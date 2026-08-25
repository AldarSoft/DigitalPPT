"""Development-only request logging without exposing request payloads."""

import logging
import time


logger = logging.getLogger("development.requests")


class DevelopmentRequestLoggingMiddleware:
    """Write one concise console line after each local request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = time.monotonic()
        response = self.get_response(request)
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.info(
            "%s %s -> %s (%.0f ms)",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        return response
