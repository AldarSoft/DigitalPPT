import type { Banner, BillingDetails, CartCapacityResponse, Category, NotificationInbox, Order, Paginated, PaymentAttempt, PaymentProvider, PaymentProviderCode, PaymentStatus, Product, Promotion, QuoteRequest, SiteSettings, StorefrontPaymentStatus, User, UserNotification } from '../types'
import type {
  AdminLicenseEvent,
  AdminLicenseEventListResponse,
  AdminLicenseFilters,
  AdminOrganizationLicenseDetail,
  AdminOrganizationLicenseListResponse,
  ClientLicenseDetail,
  ClientLicenseListResponse,
  LicenseAdjustmentInput,
  LicenseSummary,
  OrganizationInvitation,
  OrganizationNotificationInput,
  OrganizationSummaryResponse,
  OrganizationTeamResponse,
} from '../features/licensing/types'

const localApiHost =
  typeof window !== 'undefined' &&
  ['localhost', '127.0.0.1'].includes(window.location.hostname)
    ? window.location.hostname
    : '127.0.0.1'

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? `http://${localApiHost}:8000/api/v1`
export const API_ORIGIN = new URL(API_BASE).origin

let accessToken: string | null = null

export class ApiError extends Error {
  status: number
  data: unknown

  constructor(status: number, data: unknown) {
    const detail = getErrorDetail(data) ?? `Request failed with status ${status}`
    super(detail)
    this.status = status
    this.data = data
  }
}

function getErrorDetail(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  if ('detail' in data) return String((data as { detail: unknown }).detail)

  const [field, value] = Object.entries(data)[0] ?? []
  if (!field) return null
  const message = Array.isArray(value) ? value[0] : value
  return message ? String(message) : null
}

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function mediaUrl(value?: string) {
  if (!value) return '/images/radio-510.png'
  if (value.startsWith('/images/')) return value
  if (/^https?:\/\//.test(value)) return value
  return `${API_ORIGIN}${value.startsWith('/') ? value : `/${value}`}`
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: 'include',
    })
  } catch {
    throw new ApiError(0, { detail: 'Cannot connect to the API server.' })
  }

  if (response.status === 401 && accessToken && retry) {
    const refreshed = await fetch(`${API_BASE}/users/auth/refresh/`, {
      method: 'POST',
      credentials: 'include',
    })
    if (refreshed.ok) {
      const payload = (await refreshed.json()) as { access: string }
      setAccessToken(payload.access)
      return request<T>(path, init, false)
    }
    setAccessToken(null)
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, data)
  return data as T
}

export const api = {
  categories: () => request<Paginated<Category> | Category[]>('/products/categories/'),
  cartCapacity: (items: Array<{ product: number; quantity: number }>) =>
    request<CartCapacityResponse>('/licensing/cart-capacity/', {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),
  organizationSummary: () =>
    request<OrganizationSummaryResponse>('/licensing/organization/summary/'),
  organizationLicenses: () =>
    request<ClientLicenseListResponse>('/licensing/organization/licenses/'),
  organizationLicense: (licenseNumber: string) =>
    request<ClientLicenseDetail>(`/licensing/licenses/${encodeURIComponent(licenseNumber)}/`),
  organizationTeam: () =>
    request<OrganizationTeamResponse>('/licensing/organization/team/'),
  inviteLicenseManager: (email: string) =>
    request<OrganizationInvitation>('/licensing/organization/invitations/', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  resendOrganizationInvitation: (invitationId: number) =>
    request<OrganizationInvitation>(`/licensing/organization/invitations/${invitationId}/resend/`, { method: 'POST' }),
  revokeOrganizationInvitation: (invitationId: number) =>
    request<OrganizationInvitation>(`/licensing/organization/invitations/${invitationId}/revoke/`, { method: 'POST' }),
  adminLicenseOrganizations: (filters: AdminLicenseFilters = {}) =>
    request<AdminOrganizationLicenseListResponse>(`/admin/licensing/organizations/${licenseQuery(filters)}`),
  adminLicenseOrganization: (organizationId: number) =>
    request<AdminOrganizationLicenseDetail>(`/admin/licensing/organizations/${organizationId}/`),
  adminLicenseHistory: (organizationId: number, page = 1) =>
    request<AdminLicenseEventListResponse>(`/admin/licensing/organizations/${organizationId}/history/?page=${page}`),
  adminLicenseNotifications: (organizationId: number, page = 1) =>
    request<AdminLicenseEventListResponse>(`/admin/licensing/organizations/${organizationId}/notifications/?page=${page}`),
  sendAdminLicenseNotification: (organizationId: number, data: OrganizationNotificationInput) =>
    request<AdminLicenseEvent>(`/admin/licensing/organizations/${organizationId}/notifications/`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  adjustAdminLicense: (organizationId: number, licenseNumber: string, data: LicenseAdjustmentInput) =>
    request<LicenseSummary>(`/admin/licensing/organizations/${organizationId}/licenses/${encodeURIComponent(licenseNumber)}/adjust/`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  products: (query = '') =>
    request<Paginated<Product> | Product[]>(`/products/catalog/${query ? `?${query}` : ''}`),
  product: (slug: string) => request<Product>(`/products/catalog/${slug}/`),
  createProduct: (data: unknown) =>
    request<Product>('/products/catalog/', { method: 'POST', body: JSON.stringify(data) }),
  updateProduct: (slug: string, data: unknown) =>
    request<Product>(`/products/catalog/${slug}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteProduct: (slug: string) =>
    request<void>(`/products/catalog/${slug}/`, { method: 'DELETE' }),
  uploadProductImage: (image: File) => {
    const body = new FormData()
    body.append('image', image)
    return request<{ image_url: string }>('/products/upload-image/', { method: 'POST', body })
  },
  login: (data: { email: string; password: string }) =>
    request<{ user: User; access: string }>('/users/auth/login/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  register: (data: unknown) =>
    request<{ user: User; access: string }>('/users/auth/register/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  refresh: () =>
    request<{ access: string }>('/users/auth/refresh/', { method: 'POST' }, false),
  me: () => request<User>('/users/auth/me/'),
  updateMe: (data: unknown) =>
    request<User>('/users/auth/me/', { method: 'PATCH', body: JSON.stringify(data) }),
  logout: () => request<void>('/users/auth/logout/', { method: 'POST' }),
  users: (query = '') =>
    request<Paginated<User> | User[]>(`/users/accounts/${query ? `?${query}` : ''}`),
  createUser: (data: unknown) =>
    request<User>('/users/accounts/', { method: 'POST', body: JSON.stringify(data) }),
  updateUser: (id: number, data: unknown) =>
    request<User>(`/users/accounts/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteUser: (id: number) =>
    request<void>(`/users/accounts/${id}/`, { method: 'DELETE' }),
  resetPassword: (email: string) =>
    request<{ detail: string }>('/users/auth/password-reset/', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  orders: (query = '') =>
    request<Paginated<Order> | Order[]>(`/orders/${query ? `?${query}` : ''}`),
  checkout: (data: unknown) =>
    request<Order>('/orders/checkout/', { method: 'POST', body: JSON.stringify(data) }),
  updateOrder: (orderNumber: string, status: Order['status']) =>
    request<Pick<Order, 'status' | 'updated_at'>>(`/orders/${orderNumber}/`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  paymentStatus: () => request<PaymentStatus>('/payments/status/'),
  storefrontPaymentStatus: () => request<StorefrontPaymentStatus>('/payments/storefront-status/'),
  createPaymentSession: (data: {
    order_number: string
    provider: PaymentProviderCode
    idempotency_key: string
    billing: BillingDetails
  }) => request<PaymentAttempt>('/payments/checkout-sessions/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  paymentSession: (sessionId: string) =>
    request<PaymentAttempt>(`/payments/checkout-sessions/${sessionId}/`),
  simulatePaymentSession: (sessionId: string, outcome: 'succeeded' | 'failed') =>
    request<PaymentAttempt>(`/payments/checkout-sessions/${sessionId}/simulate/`, {
      method: 'POST',
      body: JSON.stringify({ outcome }),
    }),
  paymentAttempts: (query = '') =>
    request<Paginated<PaymentAttempt> | PaymentAttempt[]>(`/payments/attempts/${query ? `?${query}` : ''}`),
  simulatePayment: (data: {
    order_number: string
    provider: PaymentProviderCode
    outcome: PaymentAttempt['status']
  }) => request<PaymentAttempt>('/payments/attempts/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  updatePaymentProvider: (id: number, data: Pick<PaymentProvider, 'is_enabled'>) =>
    request<PaymentProvider>(`/payments/providers/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  notifications: () => request<NotificationInbox>('/core/notifications/'),
  readNotification: (id: number) =>
    request<UserNotification>(`/core/notifications/${id}/read/`, { method: 'PATCH' }),
  quotes: (query = '') =>
    request<Paginated<QuoteRequest> | QuoteRequest[]>(`/quotes/${query ? `?${query}` : ''}`),
  quote: (quoteNumber: string) => request<QuoteRequest>(`/quotes/${quoteNumber}/`),
  createQuote: (data: unknown) =>
    request<QuoteRequest>('/quotes/', { method: 'POST', body: JSON.stringify(data) }),
  updateQuote: (quoteNumber: string, data: { status: QuoteRequest['status'] }) =>
    request<QuoteRequest>(`/quotes/${quoteNumber}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  issueQuoteInvoice: (quoteNumber: string, data: {
    items: Array<{ id: number; quoted_unit_price: string }>
    quoted_shipping: string
    admin_message: string
  }) => request<QuoteRequest>(`/quotes/${quoteNumber}/invoice/`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  addQuoteMessage: (quoteNumber: string, body: string) =>
    request<QuoteRequest>(`/quotes/${quoteNumber}/messages/`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    }),
  cancelQuote: (quoteNumber: string) =>
    request<QuoteRequest>(`/quotes/${quoteNumber}/cancel/`, { method: 'POST' }),
  promotions: (query = '') =>
    request<Paginated<Promotion> | Promotion[]>(`/core/promotions/${query ? `?${query}` : ''}`),
  createPromotion: (data: unknown) =>
    request<Promotion>('/core/promotions/', { method: 'POST', body: JSON.stringify(data) }),
  updatePromotion: (id: number, data: unknown) =>
    request<Promotion>(`/core/promotions/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  deletePromotion: (id: number) =>
    request<void>(`/core/promotions/${id}/`, { method: 'DELETE' }),
  banners: () => request<Paginated<Banner> | Banner[]>('/core/banners/'),
  createBanner: (data: unknown) =>
    request<Banner>('/core/banners/', { method: 'POST', body: JSON.stringify(data) }),
  updateBanner: (id: number, data: unknown) =>
    request<Banner>(`/core/banners/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteBanner: (id: number) =>
    request<void>(`/core/banners/${id}/`, { method: 'DELETE' }),
  siteSettings: () => request<SiteSettings>('/core/site-settings/'),
  updateSiteSettings: (data: unknown) =>
    request<SiteSettings>('/core/site-settings/', { method: 'PATCH', body: JSON.stringify(data) }),
}

function licenseQuery(filters: AdminLicenseFilters) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '') params.set(key, String(value))
  })
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function unwrap<T>(value: Paginated<T> | T[]) {
  return Array.isArray(value) ? value : value.results
}
