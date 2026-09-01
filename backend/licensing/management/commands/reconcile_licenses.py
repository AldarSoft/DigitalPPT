from django.core.management.base import BaseCommand

from core.models import OperationalRun
from core.operations import record_run
from licensing.services import LicenseExpiryService


class Command(BaseCommand):
    help = "Reconcile license expiry statuses and create due portal and email notifications."

    def handle(self, *args, **options):
        _, result = record_run(
            kind=OperationalRun.Kind.LICENSE_RECONCILIATION,
            operation=LicenseExpiryService.reconcile_all,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {result['processed']} license(s); "
                f"created {result['notified']} expiry notification stage(s); "
                f"checked {result['coverage_processed']} organization(s) and created "
                f"{result['coverage_notified']} license-capacity reminder(s)."
            )
        )
