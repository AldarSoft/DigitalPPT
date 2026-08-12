from django.urls import path
from rest_framework.routers import DefaultRouter

from payments.views import (
    CheckoutSessionCreateView,
    PaymentAttemptViewSet,
    PaymentProviderViewSet,
    PaymentSessionDetailView,
    PaymentSessionSimulateView,
    PaymentStatusView,
    StorefrontPaymentStatusView,
)

router = DefaultRouter()
router.register("providers", PaymentProviderViewSet, basename="payment-provider")
router.register("attempts", PaymentAttemptViewSet, basename="payment-attempt")

urlpatterns = [
    path("status/", PaymentStatusView.as_view(), name="payment-status"),
    path("storefront-status/", StorefrontPaymentStatusView.as_view(), name="storefront-payment-status"),
    path("checkout-sessions/", CheckoutSessionCreateView.as_view(), name="checkout-session-create"),
    path("checkout-sessions/<uuid:session_id>/", PaymentSessionDetailView.as_view(), name="checkout-session-detail"),
    path("checkout-sessions/<uuid:session_id>/simulate/", PaymentSessionSimulateView.as_view(), name="checkout-session-simulate"),
    *router.urls,
]
