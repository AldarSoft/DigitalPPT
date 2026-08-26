from __future__ import annotations

import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.models import NotificationJob, OperationalRun
from core.notifications import mark_job_sent, process_notification
from core.operations import record_run


class Command(BaseCommand):
    help = "Deliver queued email and Power Automate notifications with retries."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process available jobs and exit.")
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--poll-seconds", type=float, default=5.0)

    def handle(self, *args, **options):
        if options["once"]:
            _, result = record_run(
                kind=OperationalRun.Kind.NOTIFICATION_DELIVERY,
                operation=lambda: self._run_once(options["limit"]),
            )
            self.stdout.write(self.style.SUCCESS(f"Processed {result['processed']} notification job(s)."))
            return
        while True:
            processed = self._process_batch(options["limit"])
            if processed == 0:
                time.sleep(max(options["poll_seconds"], 0.5))

    def _run_once(self, limit):
        processed = self._process_batch(limit)
        return {
            "processed": processed,
            "pending_count": NotificationJob.objects.filter(status=NotificationJob.Status.PENDING).count(),
            "failed_count": NotificationJob.objects.filter(status=NotificationJob.Status.FAILED).count(),
        }

    def _process_batch(self, limit: int) -> int:
        processed = 0
        for _ in range(max(limit, 1)):
            job = self._claim_job()
            if not job:
                break

            try:
                process_notification(job.kind, job.payload)
            except Exception as exc:
                job.status = NotificationJob.Status.FAILED
                job.last_error = str(exc)[:4000]
                job.available_at = timezone.now() + timedelta(
                    seconds=settings.NOTIFICATION_RETRY_SECONDS * max(job.attempts, 1)
                )
                job.save(
                    update_fields=[
                        "status",
                        "last_error",
                        "available_at",
                        "updated_at",
                    ]
                )
                self.stderr.write(f"Notification job {job.pk} failed: {exc}")
            else:
                mark_job_sent(job)
            processed += 1
        return processed

    @staticmethod
    def _claim_job():
        now = timezone.now()
        stale_before = now - timedelta(minutes=15)
        available = (
            Q(status__in=[NotificationJob.Status.PENDING, NotificationJob.Status.FAILED])
            | Q(status=NotificationJob.Status.PROCESSING, updated_at__lt=stale_before)
        )

        with transaction.atomic():
            queryset = NotificationJob.objects.filter(
                available,
                available_at__lte=now,
                attempts__lt=settings.NOTIFICATION_MAX_ATTEMPTS,
            ).order_by("available_at", "id")
            if connection.features.has_select_for_update_skip_locked:
                queryset = queryset.select_for_update(skip_locked=True)
            else:
                queryset = queryset.select_for_update()
            job = queryset.first()
            if not job:
                return None

            job.status = NotificationJob.Status.PROCESSING
            job.attempts += 1
            job.save(update_fields=["status", "attempts", "updated_at"])
            return job
