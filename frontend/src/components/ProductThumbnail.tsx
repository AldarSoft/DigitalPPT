import { mediaUrl } from '../lib/api'
import { tw } from '../lib/tailwind-styles'

export function ProductThumbnail({ imageUrl, name }: { imageUrl?: string; name: string }) {
  return <img className={tw('record-product-image')} src={mediaUrl(imageUrl)} alt={name} />
}
