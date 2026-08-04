# Backend API Notes

This app adds the production-style API surface for the current frontend without wiring the frontend to it yet.

## Routing

- Frontend-ready API prefix: `/api/v1/`
- Existing test app remains available at: `/api/test-items/`

## Main endpoint groups

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/register/`
- `GET /api/v1/store/categories/`
- `GET /api/v1/store/products/`
- `GET /api/v1/store/products/featured/`
- `GET /api/v1/store/products/best-sellers/`
- `GET /api/v1/store/products/slug/<slug>/`
- `GET /api/v1/store/products/<id>/related/`
- `GET /api/v1/store/orders/by-user/?email=<email>`
- `POST /api/v1/store/quotes/`
- `GET /api/v1/store/banners/`
- `GET /api/v1/store/testimonials/`
- `GET /api/v1/store/settings/`

- `GET /api/v1/admin/dashboard/stats/`
- `GET /api/v1/admin/dashboard/recent-orders/`
- `GET|POST /api/v1/admin/products/`
- `PATCH|DELETE /api/v1/admin/products/<id>/`
- `GET|POST /api/v1/admin/categories/`
- `PATCH|DELETE /api/v1/admin/categories/<id>/`
- `GET /api/v1/admin/orders/`
- `PATCH /api/v1/admin/orders/<id>/status/`
- `GET /api/v1/admin/quotes/`
- `PATCH /api/v1/admin/quotes/<id>/status/`
- `GET /api/v1/admin/customers/`
- `GET|POST /api/v1/admin/admins/`
- `PATCH|DELETE /api/v1/admin/admins/<id>/`
- `GET|POST /api/v1/admin/content/banners/`
- `PATCH|DELETE /api/v1/admin/content/banners/<id>/`
- `GET|POST /api/v1/admin/content/testimonials/`
- `PATCH|DELETE /api/v1/admin/content/testimonials/<id>/`
- `GET|PATCH /api/v1/admin/settings/`

## Notes

- Response shapes were aligned to the frontend mock service layer where possible.
- Products use the same paginated `{ items, total, page, totalPages, limit }` structure as the mock service.
- The frontend is still mock-based right now. Hookup can be done later by replacing `frontend/src/mock/services.js` with real API calls.
