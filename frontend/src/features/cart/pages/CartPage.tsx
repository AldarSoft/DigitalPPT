import { ArrowRight, Clock3, FileText, Minus, Plus, ShoppingBag } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useCart } from '../../../contexts/CartContext'
import { mediaUrl } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'

export function CartPage() {
    const cart = useCart();
    const canRequestQuote = cart.items.length > 0;
    return (<main className={tw("cart-page")}>
      <section className={tw("page-title")}>
        <div className={tw("shell page-title-content")}>
          <p className={tw("eyebrow")}>HOME&nbsp;&nbsp;/&nbsp;&nbsp;CART</p>
          <h1>Your cart</h1>
          <p>{cart.count} {cart.count === 1 ? 'item' : 'items'} ready for a quote</p>
        </div>
      </section>
      <section className={tw("cart-content")}>
        <div className={tw("shell cart-grid")}>
          <div className={tw("cart-list")}>
            {cart.items.length ? (<>
                <div className={tw("cart-list-head")} aria-hidden="true">
                  <span>Product</span>
                  <span>Subtotal</span>
                </div>
                {cart.items.map(({ product, quantity }) => {
                const image = product.images[0];
                const inStock = product.inventory_quantity > 0;
                return (<article className={tw("cart-item")} key={product.id}>
                      <Link className={tw("cart-item-image")} to={`/products/${product.slug}`} aria-label={`View ${product.name}`}>
                        <img src={mediaUrl(image?.image_url)} alt={image?.alt_text || product.name}/>
                      </Link>
                      <div className={tw("cart-item-copy")}>
                        <Link to={`/products/${product.slug}`}><h2>{product.name}</h2></Link>
                        <p>SKU&nbsp;&nbsp;{product.sku}</p>
                        <span className={tw(inStock ? '' : 'out')}><i />{inStock ? 'In stock' : 'Out of stock'}</span>
                      </div>
                      <div className={tw(`quantity-control ${inStock ? '' : 'disabled'}`)} aria-label={`Quantity for ${product.name}`} aria-disabled={!inStock}>
                        <button type="button" aria-label={`Decrease ${product.name} quantity`} disabled={!inStock || quantity <= 1} onClick={() => cart.setQuantity(product.id, quantity - 1)}>
                          <Minus size={16}/>
                        </button>
                        <strong aria-live="polite">{quantity}</strong>
                        <button type="button" aria-label={`Increase ${product.name} quantity`} disabled={!inStock || quantity >= product.inventory_quantity} onClick={() => cart.setQuantity(product.id, quantity + 1)}>
                          <Plus size={16}/>
                        </button>
                      </div>
                      <div className={tw("cart-item-price")}>
                        <strong>${(Number(product.current_price) * quantity).toFixed(2)}</strong>
                        <button type="button" onClick={() => cart.remove(product.id)}>Remove</button>
                      </div>
                    </article>);
            })}
              </>) : (<div className={tw("empty-state cart-empty-full")}>
                <ShoppingBag size={32}/>
                <h3>Your cart is empty</h3>
                <p>Browse field-ready radios and accessories to get started.</p>
                <Link className={tw("primary-action")} to="/shop">Browse catalog <ArrowRight size={17}/></Link>
              </div>)}
          </div>
          <aside className={tw("order-summary")}>
            <h2>Quote summary</h2>
            <dl>
              <div><dt>Estimated subtotal</dt><dd>${cart.subtotal.toFixed(2)}</dd></div>
              <div><dt>Availability</dt><dd>Confirmed by our team</dd></div>
              <div className={tw("summary-total")}><dt>Quote estimate</dt><dd>${cart.subtotal.toFixed(2)}</dd></div>
            </dl>
            {canRequestQuote ? (<Link className={tw("primary-action")} to="/checkout">
                Request a quote <ArrowRight size={18}/>
              </Link>) : (<span className={tw("primary-action disabled")} aria-disabled="true">
                Request a quote <FileText size={18}/>
              </span>)}
            <div className={tw("checkout-coming-soon")}><Clock3 size={18}/><span><strong>Online checkout coming soon</strong><small>Payment and direct ordering are not available yet.</small></span></div>
            <p><FileText size={16}/>A specialist will review and confirm your quote</p>
          </aside>
        </div>
      </section>
    </main>);
}
