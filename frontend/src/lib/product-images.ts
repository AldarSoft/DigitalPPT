import type { Product, ProductImage } from '../types'

export function orderedProductImages(images: ProductImage[]) {
  return [...images].sort(
    (a, b) =>
      Number(b.is_primary) - Number(a.is_primary) ||
      a.sort_order - b.sort_order ||
      (a.id ?? 0) - (b.id ?? 0),
  )
}

export function primaryProductImage(product: Pick<Product, 'images'>) {
  return orderedProductImages(product.images)[0]
}
