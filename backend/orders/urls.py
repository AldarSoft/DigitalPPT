from rest_framework.routers import DefaultRouter

from orders.views import CheckoutViewSet, OrderViewSet

router = DefaultRouter()
router.register("checkout", CheckoutViewSet, basename="checkout")
router.register("", OrderViewSet, basename="order")

urlpatterns = router.urls
