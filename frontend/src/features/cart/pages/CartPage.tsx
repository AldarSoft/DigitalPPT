import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Building2, FileText, LockKeyhole, Minus, Plus, ShoppingBag } from 'lucide-react'
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
    const requiresOrganization = cart.items.some(({ product }) => product.licensing_role === 'license_product' || product.licensing_role === 'licensed_product');
    const workspacesQuery = useQuery({
      queryKey: ['licensing', 'organization', 'workspaces'],
      queryFn: api.organizationWorkspaces,
      enabled: Boolean(auth.user && !auth.user.is_staff && requiresOrganization),
      staleTime: 0,
      refetchOnMount: 'always',
    });
    if (auth.user?.is_staff) return <Navigate to="/admin" replace />
    const canContinue = cart.items.length > 0 && !cart.isCatalogRefreshing && !cart.catalogRefreshError && !cart.isLicenseCalculating && !cart.licenseCalculationError;
    const canPurchase = canContinue && cart.items.every(({ product, quantity }) => product.is_stock_tracked === false || product.inventory_quantity >= quantity);
    const hasOrganization = Boolean(workspacesQuery.data?.organizations.length);
    const organizationReady = !requiresOrganization || Boolean(auth.user && workspacesQuery.isSuccess && hasOrganization);
    const organizationCheckPending = requiresOrganization && Boolean(auth.user) && workspacesQuery.isLoading;
    const organizationCheckFailed = requiresOrganization && workspacesQuery.isError;
    const needsOrganization = requiresOrganization && auth.ready && Boolean(auth.user) && workspacesQuery.isSuccess && !hasOrganization;
    const needsSignIn = requiresOrganization && auth.ready && !auth.user;
    const canStartPayment = canPurchase && organizationReady;
    const paymentDisabledReason = cart.catalogRefreshError
      ? 'Current catalog details could not be verified. Retry the saved-cart check before continuing.'
      : cart.isCatalogRefreshing
      ? 'Checking saved cart products against the current catalog.'
      : !organizationReady
      ? 'Create an organization before purchasing licenses or licensed products.'
      : canContinue
      ? 'Requested quantity exceeds available stock. Request a quote instead.'
      : undefined;
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
                {cart.items.map((item) => {
                const { product, quantity } = item;
                const image = primaryProductImage(product);
                const availableForPayment = product.is_stock_tracked === false || product.inventory_quantity >= quantity;
                const unitPrice = unitPriceForQuantity(product, quantity);
                const bulkPriceActive = Boolean(product.bulk_minimum_quantity && product.bulk_unit_price !== null && quantity >= product.bulk_minimum_quantity);
                const availabilityLabel = item.is_automatic
                  ? `Required license - covers up to ${product.license_capacity ?? 0} products`
                  : availableForPayment
                  ? `In stock - ${product.inventory_quantity} ready`
                  : `${product.inventory_quantity} in stock - quote required`;
                return (<article className={tw("cart-item")} key={`${product.id}-${item.is_automatic ? 'automatic' : 'manual'}`}>
                      <Link className={tw("cart-item-image")} to={`/products/${product.slug}`} aria-label={`View ${product.name}`}>
                        <img src={mediaUrl(image?.image_url)} alt={image?.alt_text || product.name}/>
                      </Link>
                      <div className={tw("cart-item-copy")}>
                        <Link to={`/products/${product.slug}`}><h2>{product.name}</h2></Link>
                        <p>SKU&nbsp;&nbsp;{product.sku}</p>
                        <span className={tw(availableForPayment ? '' : 'out')}><i />{availabilityLabel}</span>
                        {item.is_automatic ? <small className={tw("automatic-license-label")}><LockKeyhole size={13}/>Automatically added - Required license</small> : null}
                      </div>
                      {item.is_automatic ? <div className={tw("quantity-control")} aria-label={`Required quantity for ${product.name}`}>
                        <LockKeyhole size={15}/>
                        <strong aria-live="polite">{quantity}</strong>
                      </div> : <div className={tw("quantity-control")} aria-label={`Quantity for ${product.name}`}>
                        <button type="button" aria-label={`Decrease ${product.name} quantity`} disabled={quantity <= 1} onClick={() => cart.setQuantity(product.id, quantity - 1)}>
                          <Minus size={16}/>
                        </button>
                        <strong aria-live="polite">{quantity}</strong>
                        <button type="button" aria-label={`Increase ${product.name} quantity`} disabled={quantity >= 1000} onClick={() => cart.setQuantity(product.id, quantity + 1)}>
                          <Plus size={16}/>
                        </button>
                      </div>}
                      <div className={tw("cart-item-price")}>
                        <small className={tw(`cart-item-unit-price ${bulkPriceActive ? 'bulk' : ''}`)}>${unitPrice.toFixed(2)} each{bulkPriceActive ? ' - Bulk price' : ''}</small>
                        <strong>${(unitPrice * quantity).toFixed(2)}</strong>
                        {item.is_automatic ? null : <button type="button" onClick={() => cart.remove(product.id)}>Remove</button>}
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
            {cart.isCatalogRefreshing ? <p>Checking saved cart products against the current catalog...</p> : null}
            {cart.catalogRefreshError ? <section className="mb-3 rounded-control border border-danger bg-danger-soft p-3 text-left text-xs text-danger" role="alert"><strong>Saved cart items could not be verified.</strong><p className="mt-1">Products, prices, or availability may have changed. Try again before requesting a quote or payment.</p><button className={tw('action-button action-button-secondary action-button-compact mt-2 w-full')} type="button" onClick={cart.retryCatalogRefresh}>Try again</button></section> : null}
            {cart.isLicenseCalculating ? <p>Calculating required license capacity...</p> : null}
            {cart.licenseCalculationError ? <p role="alert">Required license capacity could not be calculated.</p> : null}
            {organizationCheckPending ? <p>Checking organization access...</p> : null}
            {needsOrganization || needsSignIn ? <section className="mb-3 rounded-control border border-[#f1d29a] bg-warning-soft p-3 text-left text-xs text-warning" role="alert"><div className="flex items-start gap-2"><AlertTriangle className="mt-0.5 shrink-0" size={17}/><div><strong className="block text-sm text-ink">Organization required</strong><p className="mt-1 !flex !items-start !justify-start !text-left !text-warning">Licenses and licensed radio products must belong to an organization before payment.</p><Link className={tw('action-button action-button-primary action-button-compact mt-3 w-full')} to={auth.user ? '/account?tab=licenses' : '/login'}><Building2 size={16}/>{auth.user ? 'Create organization' : 'Sign in to continue'}</Link></div></div></section> : null}
            {organizationCheckFailed ? <section className="mb-3 rounded-control border border-danger bg-danger-soft p-3 text-left text-xs text-danger" role="alert"><strong>Organization access could not be checked.</strong><button className={tw('action-button action-button-secondary action-button-compact mt-2 w-full')} type="button" onClick={() => void workspacesQuery.refetch()}>Try again</button></section> : null}
            {paymentsEnabled && canStartPayment ? <Link className={tw("primary-action")} to="/payment">
              <LockKeyhole size={17}/>Proceed to payment <ArrowRight size={18}/>
            </Link> : paymentsEnabled ? <button className={tw("primary-action disabled")} type="button" disabled title={paymentDisabledReason}>
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
