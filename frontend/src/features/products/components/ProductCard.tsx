import { tw } from "../../../lib/tailwind-styles";
import { ArrowUpRight, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useCart } from '../../../contexts/CartContext';
import { mediaUrl } from '../../../lib/api';
import type { Product } from '../../../types';
import { primaryProductImage } from '../../../lib/product-images';
export function ProductCard({ product }: {
    product: Product;
}) {
    const cart = useCart();
    const image = primaryProductImage(product);
    const isAvailable = product.is_stock_tracked === false || product.inventory_quantity > 0;
    const availabilityLabel = product.is_stock_tracked === false
        ? `${product.license_term_days ?? 365}-day digital license`
        : product.inventory_quantity > 0
            ? `In stock - ${product.inventory_quantity}`
            : 'Out of stock';
    return (<article className={tw("catalog-card")}>
      <Link className={tw("catalog-card-link")} to={`/products/${product.slug}`} aria-label={`View ${product.name}`}/>
      <div className={tw(`catalog-card-image ${product.licensing_role === 'license_product' ? 'license' : ''}`)}>
        <img src={mediaUrl(image?.image_url)} alt={image?.alt_text || product.name}/>
      </div>
      <div className={tw("catalog-card-body")}>
        <p>{product.category.name.toUpperCase()}</p>
        <h3>{product.name}</h3>
        <span className={tw(isAvailable ? 'stock-ok' : 'stock-out')}>
          <i />{availabilityLabel}
        </span>
        <div>
          <strong>${Number(product.current_price).toFixed(2)}</strong>
          {isAvailable ? (<button className={tw("catalog-card-action")} type="button" aria-label={`Add ${product.name} to cart`} onClick={() => cart.add(product)}>
              <Plus size={19}/>
            </button>) : (<Link className={tw("catalog-card-action quote")} to={`/products/${product.slug}`} aria-label={`View quote options for ${product.name}`}>
              <ArrowUpRight size={19}/>
            </Link>)}
        </div>
      </div>
    </article>);
}
