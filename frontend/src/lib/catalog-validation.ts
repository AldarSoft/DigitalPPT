import type { CartItem, Product } from '../types'

export interface CatalogRefreshResult {
  productsById: Map<number, Product>
  unavailableProductIds: number[]
}

type PersistedCartItem = Pick<CartItem, 'product'>

/**
 * Saved cart data is only a convenience cache. A current catalog response is
 * required before it can be used to create a quote or payment order.
 */
export async function refreshPersistedCartProducts(
  items: PersistedCartItem[],
  loadProduct: (slug: string) => Promise<Product>,
): Promise<CatalogRefreshResult> {
  const results = await Promise.all(items.map(async ({ product }) => {
    try {
      const refreshed = await loadProduct(product.slug)
      return refreshed.id === product.id ? refreshed : null
    } catch {
      return null
    }
  }))

  const productsById = new Map<number, Product>()
  const unavailableProductIds: number[] = []

  results.forEach((product, index) => {
    if (product) productsById.set(product.id, product)
    else unavailableProductIds.push(items[index].product.id)
  })

  return { productsById, unavailableProductIds }
}
