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
  current_price: string
  inventory_quantity: number
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
}

export interface Order {
  id: number
  order_number: string
  quote_number: string | null
  user_id: number | null
  status: 'pending' | 'processing' | 'completed' | 'cancelled'
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
}

export interface QuoteRequest {
  id: number
  quote_number: string
    status: 'new' | 'reviewing' | 'quoted' | 'approved' | 'closed'
  order_number: string
  requester_company_name: string
  requester_contact_person: string
  requester_email: string
  requester_phone: string
  notes: string
  items: QuoteRequestItem[]
  created_at: string
  updated_at: string
}

export interface CartItem {
  product: Product
  quantity: number
}
