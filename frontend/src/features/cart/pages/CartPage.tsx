import { useQuery } from '@tanstack/react-query'
import { ArrowRight, FileText, LockKeyhole, Minus, Plus, ShoppingBag } from 'lucide-react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { useCart } from '../../../contexts/CartContext'
import { api, mediaUrl } from '../../../lib/api'
import { unitPriceForQuantity } from '../../../lib/pricing'
import { tw } from '../../../lib/tailwind-styles'
import { primaryProductImage } from '../../../lib/product-images'

export function CartPage() {
    const cart = useCart();
    const auth = useAuth();
    const paymentStatus = useQuery({ queryKey: ['storefront-payment-status'], queryFn: api.storefrontPaymentStatus });
    if (auth.user?.is_staff) return <Navigate to="/admin" replace />
    const canContinue = cart.items.length > 0;
    const canPurchase = canContinue && cart.items.every(({ product, quantity }) => product.inventory_quantity >= quantity);
    const paymentsEnabled = paymentStatus.data?.storefront_enabled === true;
    return (<main className={tw("cart-page")}>
      <section className={tw("page-title")}>
        <div className={tw("shell page-title-content")}>
          <p className={tw("eyebrow")}>HOME&nbsp;&nbsp;/&nbsp;&nbsp;CART</p>
          <h1>Your cart</h1>
          <p>{cart.count} {cart.count === 1 ? 'item' : 'items'} ready to order or quote</p>
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
                const image = primaryProductImage(product);
                const availableForPayment = product.inventory_quantity >= quantity;
                const unitPrice = unitPriceForQuantity(product, quantity);
                const bulkPriceActive = Boolean(product.bulk_minimum_quantity && product.bulk_unit_price !== null && quantity >= product.bulk_minimum_quantity);
                const availabilityLabel = availableForPayment
                  ? `In stock - ${product.inventory_quantity} ready`
                  : `${product.inventory_quantity} in stock - quote required`;
                return (<article className={tw("cart-item")} key={product.id}>
                      <Link className={tw("cart-item-image")} to={`/products/${product.slug}`} aria-label={`View ${product.name}`}>
                        <img src={mediaUrl(image?.image_url)} alt={image?.alt_text || product.name}/>
                      </Link>
                      <div className={tw("cart-item-copy")}>
                        <Link to={`/products/${product.slug}`}><h2>{product.name}</h2></Link>
                        <p>SKU&nbsp;&nbsp;{product.sku}</p>
                        <span className={tw(availableForPayment ? '' : 'out')}><i />{availabilityLabel}</span>
                      </div>
                      <div className={tw("quantity-control")} aria-label={`Quantity for ${product.name}`}>
                        <button type="button" aria-label={`Decrease ${product.name} quantity`} disabled={quantity <= 1} onClick={() => cart.setQuantity(product.id, quantity - 1)}>
                          <Minus size={16}/>
                        </button>
                        <strong aria-live="polite">{quantity}</strong>
                        <button type="button" aria-label={`Increase ${product.name} quantity`} disabled={quantity >= 1000} onClick={() => cart.setQuantity(product.id, quantity + 1)}>
                          <Plus size={16}/>
                        </button>
                      </div>
                      <div className={tw("cart-item-price")}>
                        <small className={tw(`cart-item-unit-price ${bulkPriceActive ? 'bulk' : ''}`)}>${unitPrice.toFixed(2)} each{bulkPriceActive ? ' - Bulk price' : ''}</small>
                        <strong>${(unitPrice * quantity).toFixed(2)}</strong>
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
            <h2>Order summary</h2>
            <dl>
              <div><dt>Subtotal</dt><dd>${cart.subtotal.toFixed(2)}</dd></div>
              <div><dt>Shipping</dt><dd>Calculated later</dd></div>
              <div className={tw("summary-total")}><dt>Estimated total</dt><dd>${cart.subtotal.toFixed(2)}</dd></div>
            </dl>
            {paymentsEnabled && canPurchase ? <Link className={tw("primary-action")} to="/payment">
              <LockKeyhole size={17}/>Proceed to payment <ArrowRight size={18}/>
            </Link> : paymentsEnabled ? <button className={tw("primary-action disabled")} type="button" disabled title={canContinue ? 'Requested quantity exceeds available stock. Request a quote instead.' : undefined}>
              <LockKeyhole size={17}/>Proceed to payment <ArrowRight size={18}/>
            </button> : <button className={tw("payment-coming-soon-button")} type="button" disabled aria-disabled="true">
              <LockKeyhole size={17}/>Online payment coming soon
            </button>}
            {canContinue ? <Link className={tw("payment-order-button")} to="/checkout">
              <FileText size={17}/>Request a quote
            </Link> : <button className={tw("payment-coming-soon-button")} type="button" disabled aria-disabled="true">
              <FileText size={17}/>Request a quote
            </button>}
            <p><FileText size={16}/>Quote requests are reviewed and priced separately</p>
          </aside>
        </div>
      </section>
    </main>);
}
