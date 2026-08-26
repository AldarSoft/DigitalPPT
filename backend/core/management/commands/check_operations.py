import json

from django.core.management.base import BaseCommand, CommandError

from core.operations import operational_status


class Command(BaseCommand):
    help = "Check scheduled license reconciliation and notification delivery health."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Print machine-readable status.")

    def handle(self, *args, **options):
        status = operational_status()
        unhealthy = (
            status["license_reconciliation"]["is_stale"]
            or status["notification_delivery"]["is_stale"]
            or status["notification_delivery"]["exhausted_count"] > 0
        )
        if options["json"]:
            self.stdout.write(json.dumps(status, default=str))
        else:
            self.stdout.write(f"License reconciliation: {status['license_reconciliation']}")
            self.stdout.write(f"Notification delivery: {status['notification_delivery']}")
        if unhealthy:
            raise CommandError("Operational checks require attention.")
