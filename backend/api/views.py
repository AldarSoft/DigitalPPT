from django.contrib.auth.models import User
from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Banner,
    Category,
    Order,
    Product,
    QuoteRequest,
    SiteSettings,
    Testimonial,
    UserProfile,
)
from .serializers import (
    AdminSiteSettingsSerializer,
    AdminWriteSerializer,
    BannerSerializer,
    CategorySerializer,
    CategoryWriteSerializer,
    LoginSerializer,
    OrderSerializer,
    ProductSerializer,
    ProductWriteSerializer,
    QuoteRequestCreateSerializer,
    QuoteRequestSerializer,
    RegisterSerializer,
    SiteSettingsSerializer,
    SiteSettingsWriteSerializer,
    TestimonialSerializer,
    UserSerializer,
)


def get_site_settings():
    # Reuse a single settings row and lazily create it the first time the API needs it.
    return SiteSettings.objects.order_by("id").first() or SiteSettings.objects.create()


def build_product_queryset(request):
    # Centralize catalog filtering and sorting so store and admin product endpoints stay aligned.
    queryset = (
        Product.objects.select_related("category")
        .prefetch_related("images", "specifications")
        .annotate(
            effective_price=Coalesce(
                "sale_price", "price", output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )
        .all()
    )
    search = request.query_params.get("search")
    category_id = request.query_params.get("categoryId")
    min_price = request.query_params.get("minPrice")
    max_price = request.query_params.get("maxPrice")
    sort = request.query_params.get("sort")

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(sku__icontains=search)
            | Q(tags__icontains=search)
        )
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    if min_price:
        queryset = queryset.filter(effective_price__gte=min_price)
    if max_price:
        queryset = queryset.filter(effective_price__lte=max_price)

    if sort == "price-asc":
        queryset = queryset.order_by("effective_price", "name")
    elif sort == "price-desc":
        queryset = queryset.order_by("-effective_price", "name")
    elif sort == "name":
        queryset = queryset.order_by("name")
    elif sort == "rating":
        queryset = queryset.order_by("-rating", "name")
    else:
        queryset = queryset.order_by("-created_at", "name")

    return queryset


class FrontendPageNumberPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "limit"
    max_page_size = 100

    def get_paginated_response(self, data):
        # Return the same pagination shape the current frontend mock service already expects.
        total = self.page.paginator.count
        limit = self.get_page_size(self.request) or self.page_size
        return Response(
            {
                "items": data,
                "total": total,
                "page": self.page.number,
                "totalPages": self.page.paginator.num_pages,
                "limit": limit,
            }
        )


class HealthCheckView(APIView):
    def get(self, request):
        # Provide a lightweight endpoint for quick backend availability checks.
        return Response({"status": "ok"})


class LoginView(APIView):
    def post(self, request):
        # Validate credentials and return the flattened user payload used by the frontend.
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(UserSerializer(serializer.validated_data["user"]).data)


class RegisterView(APIView):
    def post(self, request):
        # Create a new customer account and immediately return the frontend-ready user shape.
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all().prefetch_related("products")
    serializer_class = CategorySerializer


class CategoryDetailView(generics.RetrieveAPIView):
    queryset = Category.objects.all().prefetch_related("products")
    serializer_class = CategorySerializer


class CategorySlugDetailView(generics.RetrieveAPIView):
    queryset = Category.objects.all().prefetch_related("products")
    serializer_class = CategorySerializer
    lookup_field = "slug"


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    pagination_class = FrontendPageNumberPagination

    def get_queryset(self):
        # Reuse the shared catalog query builder for the public product listing.
        return build_product_queryset(self.request)


class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.select_related("category").prefetch_related(
        "images", "specifications"
    )
    serializer_class = ProductSerializer


class ProductSlugDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.select_related("category").prefetch_related(
        "images", "specifications"
    )
    serializer_class = ProductSerializer
    lookup_field = "slug"


class FeaturedProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        # Power the home-page featured products section.
        return Product.objects.filter(is_featured=True).select_related("category").prefetch_related(
            "images", "specifications"
        )


class BestSellerProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        # Power the home-page best-seller section.
        return Product.objects.filter(is_best_seller=True).select_related(
            "category"
        ).prefetch_related("images", "specifications")


class RelatedProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        # Suggest items from the same category as the currently viewed product.
        product = Product.objects.filter(pk=self.kwargs["pk"]).first()
        if not product:
            return Product.objects.none()
        limit = int(self.request.query_params.get("limit", 4))
        return (
            Product.objects.filter(category=product.category)
            .exclude(pk=product.pk)
            .select_related("category")
            .prefetch_related("images", "specifications")[:limit]
        )


class QuoteRequestCreateView(APIView):
    def post(self, request):
        # Accept a quote request from the public form and return the saved quote summary.
        serializer = QuoteRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = serializer.save()
        return Response(
            QuoteRequestSerializer(quote).data, status=status.HTTP_201_CREATED
        )


class QuoteRequestListView(generics.ListAPIView):
    queryset = QuoteRequest.objects.prefetch_related("items").all()
    serializer_class = QuoteRequestSerializer


class QuoteRequestStatusUpdateView(APIView):
    def patch(self, request, pk):
        # Let admin screens move quote requests through their simple workflow states.
        quote = generics.get_object_or_404(QuoteRequest, pk=pk)
        status_value = request.data.get("status")
        valid_statuses = {choice[0] for choice in QuoteRequest.Status.choices}
        if status_value not in valid_statuses:
            return Response(
                {"detail": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST
            )
        quote.status = status_value
        quote.save(update_fields=["status", "updated_at"])
        return Response(QuoteRequestSerializer(quote).data)


class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer

    def get_queryset(self):
        # Support the admin orders page, with optional status filtering from the active tab.
        queryset = Order.objects.prefetch_related("items").all()
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset


class OrderDetailView(generics.RetrieveAPIView):
    queryset = Order.objects.prefetch_related("items").all()
    serializer_class = OrderSerializer


class OrderByUserListView(generics.ListAPIView):
    serializer_class = OrderSerializer

    def get_queryset(self):
        # Power account and customer-detail views by filtering orders with customer email.
        email = self.request.query_params.get("email", "")
        return Order.objects.prefetch_related("items").filter(
            customer_email__iexact=email
        )


class OrderStatusUpdateView(APIView):
    def patch(self, request, pk):
        # Let admin screens update an order's workflow status without editing the whole record.
        order = generics.get_object_or_404(Order, pk=pk)
        status_value = request.data.get("status")
        valid_statuses = {choice[0] for choice in Order.Status.choices}
        if status_value not in valid_statuses:
            return Response(
                {"detail": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST
            )
        order.status = status_value
        order.save(update_fields=["status", "updated_at"])
        return Response(OrderSerializer(order).data)


class AdminProductListCreateView(APIView):
    pagination_class = FrontendPageNumberPagination

    def get(self, request):
        # Reuse public filtering logic so admin product listings stay consistent with catalog rules.
        queryset = build_product_queryset(request)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ProductSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        # Create a product from the admin modal payload and return the normalized API shape.
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class AdminProductDetailView(APIView):
    def patch(self, request, pk):
        # Apply partial admin edits without requiring the full product payload.
        product = generics.get_object_or_404(Product, pk=pk)
        serializer = ProductWriteSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductSerializer(product).data)

    def delete(self, request, pk):
        # Remove a product selected from the admin list.
        product = generics.get_object_or_404(Product, pk=pk)
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCategoryListCreateView(APIView):
    def get(self, request):
        # Return categories with product counts for the admin categories table.
        categories = Category.objects.all().prefetch_related("products")
        return Response(CategorySerializer(categories, many=True).data)

    def post(self, request):
        # Create a category from the admin modal payload.
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(
            CategorySerializer(category).data, status=status.HTTP_201_CREATED
        )


class AdminCategoryDetailView(APIView):
    def patch(self, request, pk):
        # Apply partial admin edits to a category.
        category = generics.get_object_or_404(Category, pk=pk)
        serializer = CategoryWriteSerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(CategorySerializer(category).data)

    def delete(self, request, pk):
        # Remove a category selected from the admin list.
        category = generics.get_object_or_404(Category, pk=pk)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCustomerListView(generics.ListAPIView):
    serializer_class = UserSerializer

    def get_queryset(self):
        # Limit this admin listing to customer accounts only.
        return User.objects.filter(profile__role=UserProfile.Role.CUSTOMER).select_related(
            "profile"
        )


class AdminListCreateView(APIView):
    def get(self, request):
        # Return only admin accounts for the admin-management screen.
        admins = User.objects.filter(profile__role=UserProfile.Role.ADMIN).select_related(
            "profile"
        )
        return Response(UserSerializer(admins, many=True).data)

    def post(self, request):
        # Create a new admin account from the admin-management form.
        serializer = AdminWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminDetailView(APIView):
    def patch(self, request, pk):
        # Update a single admin account selected from the admin-management screen.
        user = generics.get_object_or_404(User, pk=pk)
        serializer = AdminWriteSerializer(
            user, data=request.data, partial=True, context={"instance": user}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data)

    def delete(self, request, pk):
        # Delete a single admin account selected from the admin-management screen.
        user = generics.get_object_or_404(User, pk=pk)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BannerListCreateView(APIView):
    def get(self, request):
        # Return banner content for both the storefront and admin content screens.
        banners = Banner.objects.all()
        return Response(BannerSerializer(banners, many=True).data)

    def post(self, request):
        # Create a banner entry from admin content tools.
        serializer = BannerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        banner = serializer.save()
        return Response(BannerSerializer(banner).data, status=status.HTTP_201_CREATED)


class BannerDetailView(APIView):
    def patch(self, request, pk):
        # Update a single banner without replacing the full object.
        banner = generics.get_object_or_404(Banner, pk=pk)
        serializer = BannerSerializer(banner, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        banner = serializer.save()
        return Response(BannerSerializer(banner).data)

    def delete(self, request, pk):
        # Delete a single banner selected from admin content tools.
        banner = generics.get_object_or_404(Banner, pk=pk)
        banner.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TestimonialListCreateView(APIView):
    def get(self, request):
        # Return testimonial content for both the storefront and admin content screens.
        testimonials = Testimonial.objects.all()
        return Response(TestimonialSerializer(testimonials, many=True).data)

    def post(self, request):
        # Create a testimonial entry from admin content tools.
        serializer = TestimonialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        testimonial = serializer.save()
        return Response(
            TestimonialSerializer(testimonial).data, status=status.HTTP_201_CREATED
        )


class TestimonialDetailView(APIView):
    def patch(self, request, pk):
        # Update a single testimonial without replacing the full object.
        testimonial = generics.get_object_or_404(Testimonial, pk=pk)
        serializer = TestimonialSerializer(testimonial, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        testimonial = serializer.save()
        return Response(TestimonialSerializer(testimonial).data)

    def delete(self, request, pk):
        # Delete a single testimonial selected from admin content tools.
        testimonial = generics.get_object_or_404(Testimonial, pk=pk)
        testimonial.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicSettingsView(APIView):
    def get(self, request):
        # Expose only storefront-safe settings fields to the public side of the app.
        return Response(SiteSettingsSerializer(get_site_settings()).data)


class AdminSettingsView(APIView):
    def get(self, request):
        # Return the full settings payload, including admin-only email configuration fields.
        return Response(AdminSiteSettingsSerializer(get_site_settings()).data)

    def patch(self, request):
        # Apply partial settings updates from the admin settings screen.
        settings_obj = get_site_settings()
        serializer = SiteSettingsWriteSerializer(
            settings_obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AdminSiteSettingsSerializer(settings_obj).data)


class DashboardStatsView(APIView):
    def get(self, request):
        # Aggregate high-level counts and totals for the admin dashboard cards.
        completed_orders = Order.objects.filter(status=Order.Status.COMPLETED)
        total_revenue = completed_orders.aggregate(total=Sum("total")).get("total") or 0
        data = {
            "totalOrders": Order.objects.count(),
            "totalRevenue": total_revenue,
            "totalProducts": Product.objects.count(),
            "totalCustomers": User.objects.filter(
                profile__role=UserProfile.Role.CUSTOMER
            ).count(),
            "pendingOrders": Order.objects.filter(status=Order.Status.PENDING).count(),
            "processingOrders": Order.objects.filter(
                status=Order.Status.PROCESSING
            ).count(),
            "completedOrders": completed_orders.count(),
            "monthlyRevenue": total_revenue,
            "revenueGrowth": 0,
            "orderGrowth": 0,
        }
        return Response(data)


class DashboardRecentOrdersView(generics.ListAPIView):
    serializer_class = OrderSerializer

    def get_queryset(self):
        # Return the most recent orders for the admin dashboard activity table.
        limit = int(self.request.query_params.get("limit", 5))
        return Order.objects.prefetch_related("items").order_by("-created_at", "-id")[:limit]
