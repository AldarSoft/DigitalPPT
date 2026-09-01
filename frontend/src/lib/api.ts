import type { Banner, BillingDetails, CartCapacityResponse, Category, NotificationInbox, Order, Paginated, PaymentAttempt, PaymentProvider, PaymentProviderCode, PaymentStatus, Product, Promotion, QuoteRequest, SiteSettings, StorefrontPaymentStatus, User, UserNotification } from '../types'
import { createRefreshCoordinator } from './session-refresh'
import type {
  AdminLicenseEvent,
  AdminLicenseEventListResponse,
  AdminLicenseFilters,
  AdminOrganizationLicenseDetail,
  AdminOrganizationLicenseListResponse,
  AdminOrganizationUsers,
  AdminOrganizationCreateInput,
  AdminOrganizationCreateResponse,
  ClientLicenseDetail,
  LicenseRenewalSummary,
  ClientLicenseListResponse,
  LicenseAdjustmentInput,
  LicenseSummary,
  OrganizationInvitation,
  OrganizationInvitationAcceptance,
  OrganizationCreateInput,
  OrganizationNotificationInput,
  OrganizationSummaryResponse,
  OrganizationTeamResponse,
  OrganizationWorkspaceListResponse,
  OrganizationSettings,
} from '../features/licensing/types'

const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim()
export const API_BASE = (configuredApiBase || '/api/v1').replace(/\/$/, '')
export const API_ORIGIN = new URL(
  API_BASE,
  typeof window === 'undefined' ? 'http://localhost' : window.location.origin,
).origin

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

const refreshAccessToken = createRefreshCoordinator(async () => {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/users/auth/refresh/`, {
      method: 'POST',
      credentials: 'include',
    })
  } catch {
    throw new ApiError(0, { detail: 'Cannot connect to the API server.' })
  }

  const data = await response.json().catch(() => null)
  if (!response.ok || !data || typeof data !== 'object' || !('access' in data)) {
    throw new ApiError(response.status, data)
  }

  const token = String(data.access)
  setAccessToken(token)
  return token
})

export function mediaUrl(value?: string) {
  if (!value) return '/images/radio-510.png'
  if (value.startsWith('/images/')) return value
  if (/^https?:\/\//.test(value)) return value
  return `${API_ORIGIN}${value.startsWith('/') ? value : `/${value}`}`
}

export interface AuthSuccess {
  user: User
  access: string
}

export interface StaffMfaChallenge {
  mfa_required: true
  challenge: string
  detail: string
}

async function requestResponse(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<Response> {
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
    try {
      await refreshAccessToken()
      return requestResponse(path, init, false)
    } catch {
      setAccessToken(null)
    }
  }

  return response
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await requestResponse(path, init)

  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, data)
  return data as T
}

async function download(path: string, filename: string) {
  const response = await requestResponse(path)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new ApiError(response.status, data)
  }

  const objectUrl = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

export const api = {
  categories: () => request<Paginated<Category> | Category[]>('/products/categories/'),
  downloadQuoteInvoice: (quoteNumber: string, invoiceNumber: string) =>
    download(
      `/quotes/${encodeURIComponent(quoteNumber)}/invoice-pdf/`,
      `${invoiceNumber || quoteNumber}.pdf`,
    ),
  cartCapacity: (items: Array<{ product: number; quantity: number }>) =>
    request<CartCapacityResponse>('/licensing/cart-capacity/', {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),
  organizationWorkspaces: () => request<OrganizationWorkspaceListResponse>('/licensing/organizations/'),
  createOrganization: (data: OrganizationCreateInput) =>
    request<OrganizationWorkspaceListResponse>('/licensing/organizations/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  organizationSummary: (organizationId?: number | null) =>
    request<OrganizationSummaryResponse>(`/licensing/organization/summary/${organizationQuery(organizationId)}`),
  organizationLicenses: (organizationId?: number | null) =>
    request<ClientLicenseListResponse>(`/licensing/organization/licenses/${organizationQuery(organizationId)}`),
  organizationLicense: (licenseNumber: string, organizationId?: number | null) =>
    request<ClientLicenseDetail>(`/licensing/licenses/${encodeURIComponent(licenseNumber)}/${organizationQuery(organizationId)}`),
  cancelOrganizationLicense: (licenseNumber: string, organizationId: number | null, data: { password: string; reason: string }) =>
    request<LicenseSummary>(`/licensing/licenses/${encodeURIComponent(licenseNumber)}/cancel/${organizationQuery(organizationId)}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  licenseRenewalSummary: (licenseNumber: string, organizationId?: number | null) =>
    request<LicenseRenewalSummary>(`/licensing/licenses/${encodeURIComponent(licenseNumber)}/renew/${organizationQuery(organizationId)}`),
  organizationTeam: (organizationId?: number | null) =>
    request<OrganizationTeamResponse>(`/licensing/organization/team/${organizationQuery(organizationId)}`),
  organizationSettings: (organizationId?: number | null) =>
    request<OrganizationSettings>(`/licensing/organization/settings/${organizationQuery(organizationId)}`),
  updateOrganizationSettings: (data: Pick<OrganizationSettings, 'name' | 'billing_email'>, organizationId?: number | null) =>
    request<OrganizationSettings>(`/licensing/organization/settings/${organizationQuery(organizationId)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  inviteLicenseManager: (email: string, organizationId?: number | null) =>
    request<OrganizationInvitation>(`/licensing/organization/invitations/${organizationQuery(organizationId)}`, {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  resendOrganizationInvitation: ({ invitationId, organizationId }: { invitationId: number; organizationId?: number | null }) =>
    request<OrganizationInvitation>(`/licensing/organization/invitations/${invitationId}/resend/${organizationQuery(organizationId)}`, { method: 'POST' }),
  revokeOrganizationInvitation: ({ invitationId, organizationId }: { invitationId: number; organizationId?: number | null }) =>
    request<OrganizationInvitation>(`/licensing/organization/invitations/${invitationId}/revoke/${organizationQuery(organizationId)}`, { method: 'POST' }),
  transferOrganizationOwnership: ({ membershipId, organizationId }: { membershipId: number; organizationId?: number | null }) =>
    request<OrganizationTeamResponse>(`/licensing/organization/ownership-transfer/${organizationQuery(organizationId)}`, {
      method: 'POST',
      body: JSON.stringify({ membership_id: membershipId }),
    }),
  acceptOrganizationInvitation: (token: string) =>
    request<OrganizationInvitationAcceptance>('/licensing/organization/invitations/accept/', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  adminLicenseOrganizations: (filters: AdminLicenseFilters = {}) =>
    request<AdminOrganizationLicenseListResponse>(`/admin/licensing/organizations/${licenseQuery(filters)}`),
  createAdminOrganization: (data: AdminOrganizationCreateInput) =>
    request<AdminOrganizationCreateResponse>('/admin/licensing/organizations/', { method: 'POST', body: JSON.stringify(data) }),
  adminLicenseOrganization: (organizationId: number) =>
    request<AdminOrganizationLicenseDetail>(`/admin/licensing/organizations/${organizationId}/`),
  adminOrganizationUsers: (organizationId: number) =>
    request<AdminOrganizationUsers>(`/admin/licensing/organizations/${organizationId}/users/`),
  inviteAdminOrganizationLicenseManager: (organizationId: number, email: string) =>
    request<OrganizationInvitation>(`/admin/licensing/organizations/${organizationId}/users/invitations/`, { method: 'POST', body: JSON.stringify({ email }) }),
  transferAdminOrganizationOwnership: (organizationId: number, membershipId: number) =>
    request<AdminOrganizationUsers>(`/admin/licensing/organizations/${organizationId}/users/ownership-transfer/`, { method: 'POST', body: JSON.stringify({ membership_id: membershipId }) }),
  resendAdminOrganizationInvitation: (organizationId: number, invitationId: number) =>
    request<OrganizationInvitation>(`/admin/licensing/organizations/${organizationId}/users/invitations/${invitationId}/resend/`, { method: 'POST' }),
  revokeAdminOrganizationInvitation: (organizationId: number, invitationId: number) =>
    request<OrganizationInvitation>(`/admin/licensing/organizations/${organizationId}/users/invitations/${invitationId}/revoke/`, { method: 'POST' }),
  adminLicenseHistory: (organizationId: number, page = 1, pageSize = 5) =>
    request<AdminLicenseEventListResponse>(`/admin/licensing/organizations/${organizationId}/history/?page=${page}&page_size=${pageSize}`),
  adminLicenseNotifications: (organizationId: number, page = 1) =>
    request<AdminLicenseEventListResponse>(`/admin/licensing/organizations/${organizationId}/notifications/?page=${page}`),
  sendAdminLicenseNotification: (organizationId: number, data: OrganizationNotificationInput) =>
    request<AdminLicenseEvent>(`/admin/licensing/organizations/${organizationId}/notifications/`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  sendAdminRenewalInvoice: (organizationId: number) =>
    request<AdminLicenseEvent>(`/admin/licensing/organizations/${organizationId}/renewal-invoice/`, {
      method: 'POST',
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
  adjustInventory: (slug: string, data: { mode: 'add' | 'set'; quantity: number; reason: string }) =>
    request<Product>(`/products/catalog/${slug}/inventory-adjust/`, {
      method: 'POST',
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
    request<AuthSuccess | StaffMfaChallenge>('/users/auth/login/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  register: (data: unknown) =>
    request<{ detail: string; email: string }>('/users/auth/register/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  verifyEmail: (token: string) =>
    request<AuthSuccess>('/users/auth/verify-email/', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  resendVerification: (email: string) =>
    request<{ detail: string }>('/users/auth/resend-verification/', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  verifyStaffMfa: (challenge: string, code: string) =>
    request<AuthSuccess>('/users/auth/staff-mfa/', {
      method: 'POST',
      body: JSON.stringify({ challenge, code }),
    }),
  refresh: async () => ({ access: await refreshAccessToken() }),
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
  confirmPasswordReset: (data: {
    uid: string
    token: string
    new_password: string
    confirm_password: string
  }) => request<{ detail: string }>('/users/auth/password-reset/confirm/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  orders: (query = '') =>
    request<Paginated<Order> | Order[]>(`/orders/${query ? `?${query}` : ''}`),
  checkout: (data: unknown) =>
    request<Order>('/orders/checkout/', { method: 'POST', body: JSON.stringify(data) }),
  createManualOrder: (data: unknown) =>
    request<Order>('/orders/manual/', { method: 'POST', body: JSON.stringify(data) }),
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
  createLicenseRenewalPaymentSession: (data: {
    license_number: string
    organization?: number | null
    provider: PaymentProviderCode
    idempotency_key: string
    billing: BillingDetails
  }) => request<PaymentAttempt>('/payments/license-renewal-sessions/', {
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
  updatePaymentProvider: (id: number, data: Partial<Pick<PaymentProvider, 'is_enabled' | 'is_customer_available'>>) =>
    request<PaymentProvider>(`/payments/providers/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  confirmBankTransfer: (orderNumber: string, data: { bank_transaction_reference: string; internal_note?: string }) =>
    request<PaymentAttempt>(`/payments/orders/${encodeURIComponent(orderNumber)}/confirm-bank-transfer/`, {
      method: 'POST',
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
  quoteClaimAccess: (quoteNumber: string, token: string) =>
    request<{ requester_email: string }>(`/quotes/${encodeURIComponent(quoteNumber)}/claim-access/?token=${encodeURIComponent(token)}`),
  claimQuote: (quoteNumber: string, token: string) =>
    request<QuoteRequest>(`/quotes/${encodeURIComponent(quoteNumber)}/claim/`, {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
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
  adminSiteSettings: () => request<SiteSettings>('/core/site-settings/admin/'),
  updateSiteSettings: (data: unknown) =>
    request<SiteSettings>('/core/site-settings/admin/', { method: 'PATCH', body: JSON.stringify(data) }),
}

function organizationQuery(organizationId?: number | null) {
  return organizationId ? `?organization=${organizationId}` : ''
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
