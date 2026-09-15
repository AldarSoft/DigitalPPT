import { test } from 'node:test'
import assert from 'node:assert/strict'
import { visibleAssurances } from './product-presentation.ts'
import type { ProductContentItem, StorefrontPaymentStatus } from '../types.ts'

const items: ProductContentItem[] = [
  { id: 'payment', icon: 'lock-keyhole', title: 'Secure payment', description: '', active: true },
  { id: 'delivery', icon: 'truck', title: 'Delivery', description: '', active: true },
  { id: 'warranty', icon: 'shield-check', title: 'Warranty', description: '', active: false },
]
test('payment claims require an available live provider and preserve badge order', () => {
  const live: StorefrontPaymentStatus = { storefront_enabled: true, development_simulator: false, manual_bank_transfer_enabled: false, providers: [{ code: 'stripe', display_name: 'Stripe', test_mode: false, sort_order: 0 }] }
  assert.deepEqual(visibleAssurances(items).map((item) => item.id), ['delivery'])
  assert.deepEqual(visibleAssurances(items, live).map((item) => item.id), ['payment', 'delivery'])
  for (const status of [{ ...live, storefront_enabled: false }, { ...live, development_simulator: true }, { ...live, providers: [] }, { ...live, providers: [{ ...live.providers[0], test_mode: true }] }]) {
    assert.deepEqual(visibleAssurances(items, status).map((item) => item.id), ['delivery'])
  }
})
