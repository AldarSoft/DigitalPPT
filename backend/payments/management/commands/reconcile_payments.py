from django.conf import settings
from django.core.management.base import BaseCommand

from payments.models import PaymentAttempt, PaymentProvider
from payments.providers import get_provider_adapter, provider_is_available
from payments.services import PaymentService


class Command(BaseCommand):
    help = "Expire stale checkout sessions and reconcile registered live providers."

    def handle(self, *args, **options):
        expired = PaymentService.expire_pending_attempts()
        reconciled = 0
        for provider in PaymentProvider.objects.filter(is_enabled=True, test_mode=False):
            adapter = get_provider_adapter(provider.code)
            if not adapter or not provider_is_available(provider):
                continue
            attempts = PaymentAttempt.objects.filter(
                provider=provider,
                status=PaymentAttempt.Status.PENDING,
            ).order_by("created_at")[:settings.PAYMENT_PROVIDER_RECONCILIATION_BATCH_SIZE]
            reconciled += adapter.reconcile_pending(attempts=attempts)
        self.stdout.write(
            self.style.SUCCESS(
                f"Expired {expired} payment session(s); reconciled {reconciled} provider payment(s)."
            )
        )
