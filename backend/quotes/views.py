from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from common.permissions import CanManageQuotes
from quotes.models import QuoteRequest
from quotes.serializers import (
    QuoteClaimSerializer,
    QuoteMessageCreateSerializer,
    QuoteInvoiceSerializer,
    QuoteRequestCreateSerializer,
    QuoteRequestSerializer,
    QuoteRequestStatusSerializer,
)
from quotes.services import QuoteService


class QuoteRequestViewSet(viewsets.ModelViewSet):
    queryset = QuoteRequest.objects.prefetch_related(
        "items__product", "orders", "messages__author"
    )
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_field = "quote_number"
    permission_classes = [IsAdminUser]
    search_fields = (
        "quote_number",
        "requester_email",
        "requester_contact_person",
        "requester_company_name",
    )
    ordering_fields = ("created_at", "status")

    def get_permissions(self):
        if self.action in {"create", "claim_access"}:
            return [AllowAny()]
        if self.action in {"partial_update", "update", "destroy"}:
            return [CanManageQuotes()]
        if self.action in {"messages", "cancel"}:
            if self.request.user and self.request.user.is_staff:
                return [CanManageQuotes()]
            return [IsAuthenticated()]
        if self.action == "claim":
            return [IsAuthenticated()]
        if self.action == "invoice":
            return [CanManageQuotes()]
        return [IsAuthenticated()]

    def get_throttles(self):
        self.throttle_scope = "quote" if self.action == "create" else None
        return super().get_throttles()

    def get_queryset(self):
        queryset = super().get_queryset().exclude(status=QuoteRequest.Status.CANCELLED)
        status_value = self.request.query_params.get("status")
        display_status = self.request.query_params.get("display_status")
        display_statuses = {
            "pending": [QuoteRequest.Status.NEW],
            "processing": [
                QuoteRequest.Status.REVIEWING,
                QuoteRequest.Status.QUOTE_APPROVED,
                QuoteRequest.Status.INVOICE_SENT,
                QuoteRequest.Status.AWAITING_PAYMENT,
                QuoteRequest.Status.PAYMENT_REJECTED,
            ],
            "completed": [QuoteRequest.Status.PAYMENT_CONFIRMED],
            "cancelled": [QuoteRequest.Status.CANCELLED],
        }
        if display_status in display_statuses:
            queryset = queryset.filter(status__in=display_statuses[display_status])
        elif status_value:
            queryset = queryset.filter(status=status_value)

        user = self.request.user
        if user and user.is_staff:
            if user.is_superuser or user.has_perm("users.manage_quotes") or user.has_perm(
                "users.confirm_bank_payments"
            ):
                return queryset
            return queryset.none()
        if not user or not user.is_authenticated:
            return queryset.none()

        return queryset.filter(user=user)

    def get_serializer_class(self):
        if self.action in {"create", "claim_access"}:
            return QuoteRequestCreateSerializer
        if self.action in {"partial_update", "update"}:
            return QuoteRequestStatusSerializer
        if self.action == "claim":
            return QuoteClaimSerializer
        return QuoteRequestSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote_request = serializer.save()
        response_serializer = QuoteRequestSerializer(
            quote_request,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @extend_schema(
        request=QuoteRequestStatusSerializer,
        responses=QuoteRequestSerializer,
    )
    def partial_update(self, request, *args, **kwargs):
        quote_request = self.get_object()
        serializer = self.get_serializer(
            quote_request,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        return self._serialize(serializer.save())

    def _serialize(self, quote_request):
        return Response(QuoteRequestSerializer(
            quote_request,
            context=self.get_serializer_context(),
        ).data)

    @action(detail=True, methods=["post"])
    def claim(self, request, quote_number=None):
        quote_request = self.queryset.filter(quote_number=quote_number).first()
        if not quote_request:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "quote_request": quote_request},
        )
        serializer.is_valid(raise_exception=True)
        return self._serialize(serializer.save())

    @action(detail=True, methods=["get"], url_path="claim-access")
    def claim_access(self, request, quote_number=None):
        quote_request = self.queryset.filter(quote_number=quote_number).first()
        if not quote_request:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        token = request.query_params.get("token", "")
        if not token:
            raise ValidationError({"token": "This quote access link is incomplete or invalid."})

        from quotes.claims import validate_guest_quote_claim_token

        validate_guest_quote_claim_token(quote_request=quote_request, token=token)
        return Response({"requester_email": quote_request.requester_email})

    @action(detail=True, methods=["post"])
    def messages(self, request, quote_number=None):
        quote_request = self.get_object()
        serializer = QuoteMessageCreateSerializer(
            data=request.data,
            context={**self.get_serializer_context(), "quote_request": quote_request},
        )
        serializer.is_valid(raise_exception=True)
        return self._serialize(serializer.save())

    @action(detail=True, methods=["post"])
    def invoice(self, request, quote_number=None):
        quote_request = self.get_object()
        serializer = QuoteInvoiceSerializer(
            data=request.data,
            context={**self.get_serializer_context(), "quote_request": quote_request},
        )
        serializer.is_valid(raise_exception=True)
        quote_request = serializer.save()
        quote_request.refresh_from_db()
        return self._serialize(quote_request)

    @action(detail=True, methods=["get"], url_path="invoice-pdf")
    def invoice_pdf(self, request, quote_number=None):
        quote_request = self.get_object()
        if not quote_request.invoice_pdf:
            return Response({"detail": "Invoice PDF is not available."}, status=status.HTTP_404_NOT_FOUND)

        response = FileResponse(
            quote_request.invoice_pdf.open("rb"),
            as_attachment=True,
            filename=f"{quote_request.invoice_number or quote_request.quote_number}.pdf",
            content_type="application/pdf",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


    @action(detail=True, methods=["post"])
    def cancel(self, request, quote_number=None):
        quote_request = QuoteService.update_status(
            quote_request=self.get_object(),
            new_status=QuoteRequest.Status.CANCELLED,
            user=request.user,
        )
        return self._serialize(quote_request)
