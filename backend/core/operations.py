from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.models import NotificationJob, OperationalRun

logger = logging.getLogger(__name__)


def record_run(*, kind: str, operation: Callable[[], dict]) -> tuple[OperationalRun, dict]:
    run = OperationalRun.objects.create(
        kind=kind,
        status=OperationalRun.Status.FAILED,
        started_at=timezone.now(),
    )
    try:
        details = operation()
    except Exception as exc:
        run.finished_at = timezone.now()
        run.error = str(exc)[:4000]
        run.save(update_fields=["finished_at", "error", "updated_at"])
        logger.exception("Operational run %s failed.", kind)
        raise
    run.status = OperationalRun.Status.SUCCEEDED
    run.finished_at = timezone.now()
    run.details = details
    run.save(update_fields=["status", "finished_at", "details", "updated_at"])
    return run, details


def operational_status(*, now=None) -> dict:
    now = now or timezone.now()
    latest_runs = {
        kind: OperationalRun.objects.filter(kind=kind, status=OperationalRun.Status.SUCCEEDED)
        .order_by("-finished_at", "-id")
        .first()
        for kind in OperationalRun.Kind.values
    }
    pending = NotificationJob.objects.filter(
        status__in=[NotificationJob.Status.PENDING, NotificationJob.Status.PROCESSING]
    )
    oldest_pending = pending.order_by("available_at", "id").first()
    notification_age = (
        max(0, int((now - oldest_pending.created_at).total_seconds()))
        if oldest_pending
        else 0
    )
    license_cutoff = now - timedelta(hours=settings.LICENSE_RECONCILIATION_MAX_AGE_HOURS)
    worker_cutoff = now - timedelta(minutes=settings.NOTIFICATION_WORKER_MAX_AGE_MINUTES)
    exhausted_count = NotificationJob.objects.filter(
        status=NotificationJob.Status.FAILED,
        attempts__gte=settings.NOTIFICATION_MAX_ATTEMPTS,
    ).count()
    return {
        "license_reconciliation": {
            "last_success_at": latest_runs[OperationalRun.Kind.LICENSE_RECONCILIATION].finished_at
            if latest_runs[OperationalRun.Kind.LICENSE_RECONCILIATION] else None,
            "is_stale": not latest_runs[OperationalRun.Kind.LICENSE_RECONCILIATION]
            or latest_runs[OperationalRun.Kind.LICENSE_RECONCILIATION].finished_at < license_cutoff,
        },
        "notification_delivery": {
            "last_success_at": latest_runs[OperationalRun.Kind.NOTIFICATION_DELIVERY].finished_at
            if latest_runs[OperationalRun.Kind.NOTIFICATION_DELIVERY] else None,
            "is_stale": bool(pending) and (
                not latest_runs[OperationalRun.Kind.NOTIFICATION_DELIVERY]
                or latest_runs[OperationalRun.Kind.NOTIFICATION_DELIVERY].finished_at < worker_cutoff
            ),
            "pending_count": pending.count(),
            "oldest_pending_age_seconds": notification_age,
            "exhausted_count": exhausted_count,
        },
    }
