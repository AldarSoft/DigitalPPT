from __future__ import annotations

import hashlib
import threading
import time
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle

from core.models import RequestThrottleBucket


class DatabaseScopedRateThrottle(ScopedRateThrottle):
    """Process-safe fixed-window throttling backed by the primary database."""

    scope_attr = "throttle_scope"
    _cleanup_lock = threading.Lock()
    _next_cleanup_at = 0.0
    cleanup_interval_seconds = 900
    cleanup_retention_seconds = 86400

    def allow_request(self, request, view):
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return True

        self.rate = api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)
        if not self.rate:
            return True
        self.num_requests, self.duration = self.parse_rate(self.rate)
        if self.num_requests <= 0:
            self.available_at = timezone.now() + timedelta(seconds=self.duration)
            return False

        self._cleanup_expired_buckets()
        now = timezone.now()
        identity = self._identity(request)
        key = hashlib.sha256(f"{self.scope}:{identity}".encode("utf-8")).hexdigest()

        for _ in range(3):
            try:
                return self._consume(key=key, now=now)
            except IntegrityError:
                # Two workers can create the first bucket simultaneously. The
                # winner commits it; the loser retries and locks that row.
                continue
        self.available_at = now + timedelta(seconds=self.duration)
        return False

    def _identity(self, request) -> str:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            return f"user:{user.pk}"
        return f"ip:{self.get_ident(request)}"

    @transaction.atomic
    def _consume(self, *, key: str, now):
        bucket = RequestThrottleBucket.objects.select_for_update().filter(key=key).first()
        if bucket is None:
            expires_at = now + timedelta(seconds=self.duration)
            RequestThrottleBucket.objects.create(
                key=key,
                scope=self.scope,
                request_count=1,
                window_started_at=now,
                expires_at=expires_at,
            )
            self.available_at = expires_at
            return True

        if bucket.expires_at <= now:
            bucket.scope = self.scope
            bucket.request_count = 1
            bucket.window_started_at = now
            bucket.expires_at = now + timedelta(seconds=self.duration)
            bucket.save(
                update_fields=[
                    "scope",
                    "request_count",
                    "window_started_at",
                    "expires_at",
                    "updated_at",
                ]
            )
            self.available_at = bucket.expires_at
            return True

        self.available_at = bucket.expires_at
        if bucket.request_count >= self.num_requests:
            return False

        bucket.request_count += 1
        bucket.save(update_fields=["request_count", "updated_at"])
        return True

    def wait(self):
        if not getattr(self, "available_at", None):
            return None
        return max((self.available_at - timezone.now()).total_seconds(), 0)

    @classmethod
    def _cleanup_expired_buckets(cls):
        monotonic_now = time.monotonic()
        if monotonic_now < cls._next_cleanup_at:
            return
        with cls._cleanup_lock:
            if monotonic_now < cls._next_cleanup_at:
                return
            cutoff = timezone.now() - timedelta(seconds=cls.cleanup_retention_seconds)
            RequestThrottleBucket.objects.filter(expires_at__lt=cutoff).delete()
            cls._next_cleanup_at = monotonic_now + cls.cleanup_interval_seconds
