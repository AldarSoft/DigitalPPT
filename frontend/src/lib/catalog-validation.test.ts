import assert from 'node:assert/strict'
import test from 'node:test'

import { refreshPersistedCartProducts } from './catalog-validation.ts'
import type { Product } from '../types'

const product = (id: number, slug = `product-${id}`) => ({ id, slug }) as Product

test('accepts a saved cart only when every product is refreshed with the same id', async () => {
  const result = await refreshPersistedCartProducts(
    [{ product: product(1) }, { product: product(2) }],
    async (slug) => product(Number(slug.split('-').at(-1)), slug),
  )

  assert.equal(result.unavailableProductIds.length, 0)
  assert.deepEqual([...result.productsById.keys()], [1, 2])
})

test('marks saved items unavailable when the catalog request fails or returns a different product', async () => {
  const result = await refreshPersistedCartProducts(
    [{ product: product(1) }, { product: product(2) }],
    async (slug) => {
      if (slug === 'product-1') throw new Error('catalog offline')
      return product(99, slug)
    },
  )

  assert.deepEqual(result.unavailableProductIds, [1, 2])
  assert.equal(result.productsById.size, 0)
})
