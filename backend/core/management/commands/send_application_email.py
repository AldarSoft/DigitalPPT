from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.html import escape

from common.email_delivery import send_application_email


class Command(BaseCommand):
    help = "Send a test message through the configured application email transport."

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="Email address that receives the test message.")

    def handle(self, *args, **options):
        recipient = options["recipient"]
        site_name = settings.SITE_NAME
        send_application_email(
            subject=f"{site_name} email test",
            text_body=(
                f"This message confirms that the {site_name} application email "
                "transport is configured correctly."
            ),
            html_body=(
                f"<h2>{escape(site_name)} email test</h2>"
                "<p>The application email transport is configured correctly.</p>"
            ),
            recipients=[recipient],
        )
        self.stdout.write(self.style.SUCCESS(f"Test email accepted for {recipient}."))
