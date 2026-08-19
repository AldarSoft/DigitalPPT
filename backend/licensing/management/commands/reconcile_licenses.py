from django.core.management.base import BaseCommand

from licensing.services import LicenseExpiryService


class Command(BaseCommand):
    help = "Reconcile license expiry statuses and create due portal notifications."

    def handle(self, *args, **options):
        result = LicenseExpiryService.reconcile_all()
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {result['processed']} license(s); "
                f"created {result['notified']} notification stage(s)."
            )
        )
