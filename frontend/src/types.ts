export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Category {
  id: number
  name: string
  slug: string
  description: string
  image_url: string
  is_active: boolean
  product_count: number
}

export interface ProductImage {
  id?: number
  image_url: string
  alt_text: string
  is_primary: boolean
  sort_order: number
}

export interface ProductSpecification {
  id?: number
  key: string
  value: string
  sort_order: number
}

export interface LicenseProductSummary {
  id: number
  name: string
  slug: string
  sku: string
  current_price: string
  license_capacity: number
  license_term_days: number
}

export interface Product {
  id: number
  name: string
  slug: string
  sku: string
  brand: string
  short_description: string
  description: string
  price: string
  cost_price?: string | null
  sale_price: string | null
  bulk_minimum_quantity: number | null
  bulk_unit_price: string | null
  current_price: string
  inventory_quantity: number
  on_hand_inventory_quantity?: number
  reserved_inventory_quantity?: number
  licensing_role: 'standard' | 'licensed_product' | 'license_product'
  required_license_product: LicenseProductSummary | null
  license_capacity: number | null
  license_term_days: number | null
  is_stock_tracked: boolean
  status: 'draft' | 'published' | 'archived'
  is_featured: boolean
  is_active: boolean
  category: Category
  images: ProductImage[]
  specifications: ProductSpecification[]
  created_at: string
  updated_at: string
}

export interface UserProfile {
  company_name: string
  job_title: string
  avatar_url: string
  address_line_1: string
  address_line_2: string
  city: string
  state: string
  country: string
  postal_code: string
  use_different_shipping_address: boolean
  shipping_address_line_1: string
  shipping_address_line_2: string
  shipping_city: string
  shipping_state: string
  shipping_country: string
  shipping_postal_code: string
}

export interface User {
  id: number
  email: string
  username: string
  first_name: string
  last_name: string
  phone_number: string
  is_customer: boolean
  is_staff: boolean
  is_active: boolean
  date_joined: string
  profile: UserProfile
  account_setup_email_queued?: boolean
}

export interface Promotion {
  id: number
  code: string
  title: string
  description: string
  discount_type: 'percentage' | 'fixed'
  discount_value: string
  starts_at: string | null
  ends_at: string | null
  usage_limit: number | null
  times_redeemed: number
  is_active: boolean
  status: 'active' | 'scheduled' | 'expired' | 'redeemed' | 'inactive'
  created_at: string
  updated_at: string
}

export interface Banner {
  id: number
  title: string
  subtitle: string
  description: string
  cta_label: string
  cta_url: string
  image_url: string
  sort_order: number
  is_active: boolean
}

export interface SiteSettings {
  site_name: string
  tagline: string
  support_email: string
  support_phone: string
  company_address: string
  facebook_url: string
  twitter_url: string
  linkedin_url: string
  instagram_url: string
  commerce_defaults_enabled: boolean
  default_currency: string
  tax_rate: string
  flat_shipping_rate: string
  free_shipping_minimum: string
  working_hours: string
  about_story: string
  about_mission: string
  about_vision: string
  about_image_url: string
  about_team: unknown[]
  about_values: unknown[]
  about_stats: unknown[]
    meta_title: string
    meta_description: string
    homepage_hero_secondary_cta_label: string
    homepage_hero_secondary_cta_url: string
    homepage_hero_stats: Array<{ value: string; label: string }>
    homepage_solution_eyebrow: string
    homepage_solution_title: string
    homepage_solution_description: string
    homepage_solution_benefits: string[]
    homepage_comparison_eyebrow: string
    homepage_comparison_title: string
    homepage_comparison_products: Array<{
      model: string
      best_for: string
      network: string
      system: string
      protection: string
      price: string
    }>
    homepage_resources_eyebrow: string
    homepage_resources_title: string
    homepage_resources: Array<{
      eyebrow: string
      title: string
      description: string
      image_url: string
      url: string
    }>
    homepage_contact_eyebrow: string
    homepage_contact_title: string
    homepage_contact_description: string
    homepage_contact_cta_label: string
    homepage_contact_cta_url: string
  }

export interface OrderItem {
  id: number
  product: number | null
  product_slug: string
  product_name: string
  sku: string
  unit_price: string
  quantity: number
  line_total: string
  image_url: string
  available_stock: number | null
  licensing_role: 'standard' | 'licensed_product' | 'license_product' | null
  license_capacity: number | null
  license_term_days: number | null
}

export interface Order {
  id: number
  order_number: string
  quote_number: string | null
  renewal_license_number: string | null
  renewal: {
    license_number: string
    license_name: string
    organization_name: string
    current_expires_on: string | null
    projected_expires_on: string | null
    term_days: number | null
  } | null
  source: 'direct' | 'quote' | 'admin'
  user_id: number | null
  is_paid: boolean
  status: 'draft' | 'pending' | 'scheduled' | 'processing' | 'completed' | 'cancelled'
  customer_first_name: string
  customer_last_name: string
  customer_email: string
  customer_phone: string
  company_name: string
  shipping_address: string
  shipping_city: string
  shipping_state: string
  shipping_postal_code: string
  shipping_country: string
  subtotal: string
  tax_amount: string
  shipping_fee: string
  total: string
  stock_deducted: boolean
  notes: string
  items: OrderItem[]
  created_at: string
  updated_at: string
}

export interface QuoteRequestItem {
  id: number
  product: number | null
  product_slug: string
  product_name: string
  sku: string
  quantity: number
  specifications: Record<string, unknown>
  quoted_unit_price: string | null
  quoted_line_total: string | null
  suggested_unit_price: string | null
  bulk_price_applied: boolean
  image_url: string
}

export interface QuoteMessage {
  id: number
  sender_role: 'admin' | 'customer'
  author_name: string
  body: string
  created_at: string
}

export interface QuoteRequest {
  id: number
  quote_number: string
  status: 'new' | 'reviewing' | 'quoted' | 'approved' | 'cancelled'
  order_number: string
  order_status: '' | 'pending' | 'scheduled' | 'processing' | 'completed' | 'cancelled'
  requester_company_name: string
  requester_contact_person: string
  requester_email: string
  requester_phone: string
  notes: string
  admin_message: string
  quoted_subtotal: string | null
  quoted_shipping: string
  quoted_total: string | null
  quoted_at: string | null
  invoice_number: string | null
  invoice_pdf_url: string
  invoiced_at: string | null
  messages: QuoteMessage[]
  items: QuoteRequestItem[]
  created_at: string
  updated_at: string
}

export interface CartItem {
  product: Product
  quantity: number
  is_automatic?: boolean
  covered_quantity?: number
  uncovered_quantity?: number
  required_for_product_names?: string[]
}

export interface CartCapacityRequirement {
  license_product: Product
  product_quantities: Array<{
    product_id: number
    product_name: string
    quantity: number
  }>
  requested_quantity: number
  covered_quantity: number
  uncovered_quantity: number
  available_capacity: number
  required_license_units: number
  provided_license_units: number
  automatic_license_units: number
}

export interface CartCapacityResponse {
  organization: { public_id: string; name: string } | null
  requirements: CartCapacityRequirement[]
}

export type PaymentProviderCode = 'stripe' | 'paypal' | 'qpay' | 'bank_transfer'

export interface PaymentProvider {
  id: number
  code: PaymentProviderCode
  display_name: string
  is_enabled: boolean
  test_mode: boolean
  api_connected: boolean
  integration_state: 'disabled' | 'development_simulator' | 'development_unavailable' | 'credentials_missing' | 'adapter_not_implemented' | 'ready'
  sort_order: number
}

export interface PaymentStatus {
  storefront_enabled: boolean
  live_processing_available: boolean
  test_mode: boolean
  providers: PaymentProvider[]
}

export interface PaymentAttempt {
  id: number
  reference: string
  order_number: string | null
  order_status: Order['status'] | null
  renewal_license_number: string | null
  provider_code: PaymentProviderCode
  provider_name: string
  amount: number | string
  currency: string
  status: 'pending' | 'succeeded' | 'failed' | 'cancelled' | 'expired' | 'refunded'
  is_test: boolean
  session_id: string
  checkout_url: string
  external_reference: string
  failure_message: string
  created_by_email: string
  expires_at: string | null
  paid_at: string | null
  created_at: string
}

export interface UserNotification {
  id: number
  title: string
  message: string
  url: string
  is_read: boolean
  created_at: string
}

export interface NotificationInbox {
  unread_count: number
  notifications: UserNotification[]
}

export interface StorefrontPaymentProvider {
  code: PaymentProviderCode
  display_name: string
  test_mode: boolean
  sort_order: number
}

export interface StorefrontPaymentStatus {
  storefront_enabled: boolean
  development_simulator: boolean
  providers: StorefrontPaymentProvider[]
}

export interface BillingDetails {
  email: string
  first_name: string
  last_name: string
  phone: string
  company: string
  address: string
  city: string
  state: string
  postal_code: string
  country: string
}
