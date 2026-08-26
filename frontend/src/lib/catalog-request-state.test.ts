import assert from 'node:assert/strict'
import test from 'node:test'

import { catalogRequestState, productRequestState } from './catalog-request-state.ts'

test('catalog outages are unavailable instead of a fallback catalog', () => {
  assert.equal(catalogRequestState({ hasData: false, isError: true, isLoading: false }), 'unavailable')
  assert.equal(catalogRequestState({ hasData: false, isError: false, isLoading: true }), 'loading')
  assert.equal(catalogRequestState({ hasData: true, isError: true, isLoading: false }), 'ready')
})

test('product errors distinguish a missing product from a retryable outage', () => {
  assert.equal(productRequestState({ hasData: false, isLoading: false, status: 404 }), 'not-found')
  assert.equal(productRequestState({ hasData: false, isLoading: false, status: 503 }), 'unavailable')
  assert.equal(productRequestState({ hasData: false, isLoading: true }), 'loading')
})
