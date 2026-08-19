TAG_RULES = (
    ("/api/v1/admin/licensing/", "License Administration"),
    ("/api/v1/users/auth/", "Authentication"),
    ("/api/v1/users/accounts/", "User Administration"),
    ("/api/v1/products/", "Product Catalog"),
    ("/api/v1/orders/checkout/", "Checkout"),
    ("/api/v1/orders/", "Orders"),
    ("/api/v1/quotes/", "Quotes"),
    ("/api/v1/payments/", "Payments"),
    ("/api/v1/licensing/", "Licensing"),
    ("/api/v1/core/notifications/", "Notifications"),
    ("/api/v1/core/contact-messages/", "Support"),
    ("/api/v1/core/", "Site Content"),
)


def categorize_operations(result, generator, request, public):
    """Assign stable domain tags so Swagger remains useful as the API grows."""
    for path, operations in result.get("paths", {}).items():
        tag = next(
            (name for prefix, name in TAG_RULES if path.startswith(prefix)),
            "Other",
        )
        for operation in operations.values():
            if isinstance(operation, dict):
                operation["tags"] = [tag]
    return result
