import type { ProductContentItem, StorefrontPaymentStatus } from '../types'

export function visibleAssurances(items: ProductContentItem[], payment?: StorefrontPaymentStatus) {
  const livePayment = payment?.storefront_enabled === true && !payment.development_simulator
    && payment.providers.some((provider) => !provider.test_mode)
  return items.filter((item) => item.active && (item.id !== 'payment' || livePayment))
}
