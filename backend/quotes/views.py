from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from quotes.models import QuoteRequest
from quotes.serializers import (
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
        if self.action == "create":
            return [AllowAny()]
        if self.action in {"partial_update", "update", "destroy"}:
            return [IsAdminUser()]
        if self.action in {"messages", "cancel"}:
            return [IsAuthenticated()]
        if self.action == "invoice":
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_throttles(self):
        self.throttle_scope = "quote" if self.action == "create" else None
        return super().get_throttles()

    def get_queryset(self):
        queryset = super().get_queryset()
        status_value = self.request.query_params.get("status")
        display_status = self.request.query_params.get("display_status")
        display_statuses = {
            "pending": [QuoteRequest.Status.NEW],
            "processing": [QuoteRequest.Status.REVIEWING, QuoteRequest.Status.QUOTED],
            "completed": [QuoteRequest.Status.APPROVED],
            "cancelled": [QuoteRequest.Status.CLOSED],
        }
        if display_status in display_statuses:
            queryset = queryset.filter(status__in=display_statuses[display_status])
        elif status_value:
            queryset = queryset.filter(status=status_value)
        else:
            queryset = queryset.exclude(status=QuoteRequest.Status.CLOSED)

        user = self.request.user
        if user and user.is_staff:
            return queryset
        if not user or not user.is_authenticated:
            return queryset.none()

        return queryset.filter(
            Q(user=user) | Q(requester_email__iexact=user.email)
        ).distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return QuoteRequestCreateSerializer
        if self.action in {"partial_update", "update"}:
            return QuoteRequestStatusSerializer
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

    def _serialize(self, quote_request):
        return Response(QuoteRequestSerializer(
            quote_request,
            context=self.get_serializer_context(),
        ).data)

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
        return self._serialize(serializer.save())


    @action(detail=True, methods=["post"])
    def cancel(self, request, quote_number=None):
        quote_request = QuoteService.update_status(
            quote_request=self.get_object(),
            new_status=QuoteRequest.Status.CLOSED,
            user=request.user,
        )
        return self._serialize(quote_request)
