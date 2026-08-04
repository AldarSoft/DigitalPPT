import { tw } from "../../../lib/tailwind-styles";
import { ArrowUpRight, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useCart } from '../../../contexts/CartContext';
import { mediaUrl } from '../../../lib/api';
import type { Product } from '../../../types';
export function ProductCard({ product }: {
    product: Product;
}) {
    const cart = useCart();
    const image = [...product.images].sort((a, b) => Number(b.is_primary) - Number(a.is_primary) || a.sort_order - b.sort_order)[0];
    return (<article className={tw("catalog-card")}>
      <Link className={tw("catalog-card-link")} to={`/products/${product.slug}`} aria-label={`View ${product.name}`}/>
      <div className={tw("catalog-card-image")}>
        <img src={mediaUrl(image?.image_url)} alt={image?.alt_text || product.name}/>
      </div>
      <div className={tw("catalog-card-body")}>
        <p>{product.category.name.toUpperCase()}</p>
        <h3>{product.name}</h3>
        <span className={tw(product.inventory_quantity > 0 ? 'stock-ok' : 'stock-out')}>
          <i />{product.inventory_quantity > 0 ? 'In stock' : 'Out of stock'}
        </span>
        <div>
          <strong>${Number(product.current_price).toFixed(2)}</strong>
          {product.inventory_quantity > 0 ? (<button className={tw("catalog-card-action")} type="button" aria-label={`Add ${product.name} to cart`} onClick={() => cart.add(product)}>
              <Plus size={19}/>
            </button>) : (<Link className={tw("catalog-card-action quote")} to={`/products/${product.slug}`} aria-label={`View quote options for ${product.name}`}>
              <ArrowUpRight size={19}/>
            </Link>)}
        </div>
      </div>
    </article>);
}
