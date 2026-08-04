import type { Banner, Category, Order, Paginated, Product, Promotion, QuoteRequest, SiteSettings, User } from '../types'

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
    const detail =
      typeof data === 'object' && data && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : `Request failed with status ${status}`
    super(detail)
    this.status = status
    this.data = data
  }
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

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })

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
    request<Order>(`/orders/${orderNumber}/`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  quotes: (query = '') =>
    request<Paginated<QuoteRequest> | QuoteRequest[]>(`/quotes/${query ? `?${query}` : ''}`),
  createQuote: (data: unknown) =>
    request<QuoteRequest>('/quotes/', { method: 'POST', body: JSON.stringify(data) }),
  updateQuote: (quoteNumber: string, status: QuoteRequest['status']) =>
    request<Pick<QuoteRequest, 'status' | 'order_number'>>(`/quotes/${quoteNumber}/`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
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

export function unwrap<T>(value: Paginated<T> | T[]) {
  return Array.isArray(value) ? value : value.results
}
