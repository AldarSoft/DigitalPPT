import type { Product } from '../types'

export function unitPriceForQuantity(product: Product, quantity: number) {
  if (
    product.bulk_minimum_quantity
    && product.bulk_unit_price !== null
    && quantity >= product.bulk_minimum_quantity
  ) {
    return Number(product.bulk_unit_price)
  }
  return Number(product.current_price)
}
