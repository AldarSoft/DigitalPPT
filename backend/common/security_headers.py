from django.conf import settings


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "").strip()
        if policy:
            response.setdefault("Content-Security-Policy", policy)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
