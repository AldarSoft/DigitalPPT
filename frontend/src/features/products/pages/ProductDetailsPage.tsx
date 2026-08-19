import { tw } from "../../../lib/tailwind-styles";
import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowUpRight, BatteryCharging, CreditCard, Info, LockKeyhole, MapPinned, MessageCircle, Minus, PackageCheck, Plus, ShieldCheck, ShoppingBag, Truck, UsersRound, } from 'lucide-react';
import { toast } from 'sonner';
import { useCart } from '../../../contexts/CartContext';
import { api, ApiError, mediaUrl, unwrap } from '../../../lib/api';
import { fallbackProducts } from '../../../lib/fallback-data';
import { unitPriceForQuantity } from '../../../lib/pricing';
import type { Product } from '../../../types';
import { orderedProductImages, primaryProductImage } from '../../../lib/product-images';
const defaultGallery = [
    {
        src: '/images/radio-510.png',
        alt: 'IPTT510 handheld radio from the front',
    },
    {
        src: '/images/radio-510-rear.png',
        alt: 'IPTT510 handheld radio rear and belt clip',
    },
    {
        src: '/images/radio-510-detail.png',
        alt: 'IPTT510 radio top and side control detail',
    },
];
const featureItems = [
    {
        icon: MessageCircle,
        title: 'One-touch communication',
        copy: 'Fast push-to-talk for individuals or teams',
    },
    {
        icon: ArrowUpRight,
        title: 'Unlimited talk range',
        copy: 'Communicate wherever cellular service is available',
    },
    {
        icon: UsersRound,
        title: 'Private and group calls',
        copy: 'Member lists, parent groups and dispatch',
    },
    {
        icon: CreditCard,
        title: 'Dual SIM card',
        copy: 'Flexible network access for dependable coverage',
    },
    {
        icon: MapPinned,
        title: 'Web dispatch ready',
        copy: 'Coordinate users and talk groups centrally',
    },
    {
        icon: BatteryCharging,
        title: 'Long-duration operation',
        copy: '3000mAh battery for the working day',
    },
];
function ProductBenefits() {
    const benefits = [
        { icon: PackageCheck, title: 'Delivery & returns', copy: 'Clear policies, secure delivery' },
        { icon: ShieldCheck, title: 'Product expertise', copy: 'Help choosing the right system' },
        { icon: CreditCard, title: 'Order confirmation', copy: 'Review before payment is enabled' },
        { icon: MessageCircle, title: 'Human support', copy: 'Talk to a radio specialist' },
    ];
    return (<section className={tw("product-benefits")} aria-label="Customer benefits">
      <div className={tw("shell product-benefit-grid")}>
        {benefits.map(({ icon: Icon, title, copy }) => (<div className={tw("product-benefit")} key={title}>
            <span><Icon size={23}/></span>
            <div>
              <strong>{title}</strong>
              <small>{copy}</small>
            </div>
          </div>))}
      </div>
    </section>);
}
export function ProductDetailsPage() {
    const cart = useCart();
    const navigate = useNavigate();
    const onAdd = (product: Product, quantity: number) => cart.add(product, quantity);
    const onBuyNow = (product: Product, quantity: number) => {
        cart.add(product, quantity);
        navigate('/cart');
    };
    const { slug = 'iptt510' } = useParams();
    const productQuery = useQuery({
        queryKey: ['product', slug],
        queryFn: () => api.product(slug),
        retry: (failureCount, error) => !(error instanceof ApiError && error.status === 404) && failureCount < 2,
    });
    const fallbackProduct = fallbackProducts.find((item) => item.slug === slug);
    const resolvedProduct = productQuery.data ?? fallbackProduct;
    const product = resolvedProduct ?? fallbackProducts[0];
    const [galleryState, setGalleryState] = useState({ productId: product.id, index: 0 });
    const relatedQuery = useQuery({
        queryKey: ['related-products', product.category.slug],
        queryFn: () => api.products(`category=${encodeURIComponent(product.category.slug)}`),
        enabled: Boolean(resolvedProduct),
    });
    const isLicenseProduct = product.licensing_role === 'license_product';
    const availableStock = Math.max(0, product.inventory_quantity);
    const maximumQuantity = product.is_stock_tracked === false ? 1000 : availableStock;
    const isOutOfStock = product.is_stock_tracked !== false && availableStock === 0;
    const [quantityState, setQuantityState] = useState({ productId: product.id, value: 1 });
    const quantity = quantityState.productId === product.id
        ? (isOutOfStock ? 0 : Math.min(Math.max(quantityState.value, 1), maximumQuantity))
        : (isOutOfStock ? 0 : 1);
    const unitPrice = unitPriceForQuantity(product, quantity);
    const bulkPriceActive = Boolean(
        product.bulk_minimum_quantity
        && product.bulk_unit_price !== null
        && quantity >= product.bulk_minimum_quantity,
    );
    const updateQuantity = (value: number) => {
        setQuantityState({
            productId: product.id,
            value: isOutOfStock ? 0 : Math.min(Math.max(value, 1), maximumQuantity),
        });
    };
    const gallery = product.images.length
        ? orderedProductImages(product.images).map((image) => ({
            src: mediaUrl(image.image_url),
            alt: image.alt_text || product.name,
        }))
        : defaultGallery;
    const activeImage = galleryState.productId === product.id
        ? Math.min(galleryState.index, gallery.length - 1)
        : 0;
    const isRadio = product.category.slug.includes('radio') && !product.category.slug.includes('holster');
    const quoteHref = `mailto:sales@digitalptt.com?subject=${encodeURIComponent(`Quote request: ${product.name}`)}&body=${encodeURIComponent(`Hello, I would like a quote for ${product.name} (SKU: ${product.sku}).`)}`;
    const relatedProducts = (relatedQuery.data ? unwrap(relatedQuery.data) : fallbackProducts)
        .filter((item) => item.category.slug === product.category.slug && item.id !== product.id)
        .slice(0, 3);
    const detailItems = [
        { key: 'Model', value: product.name },
        { key: 'SKU', value: product.sku },
        { key: 'Brand', value: product.brand },
        { key: 'Category', value: product.category.name },
        ...product.specifications,
    ];
    const detailRows = Array.from({ length: Math.ceil(detailItems.length / 2) }, (_, index) => detailItems.slice(index * 2, index * 2 + 2));
    if (!resolvedProduct) {
        return (<main className={tw("route-message shell")}>
          <MessageCircle size={32}/>
          <h1>{productQuery.isLoading ? 'Loading product...' : 'Product not found'}</h1>
          <p>{productQuery.isLoading ? 'Fetching the latest product information.' : 'This product may have been removed or its address may have changed.'}</p>
          {productQuery.isLoading ? null : <Link className={tw("primary-action")} to="/shop">Browse the catalog <ArrowUpRight size={17}/></Link>}
        </main>);
    }
    return (<main className={tw("product-page")}>
      <nav className={tw("product-breadcrumb")} aria-label="Breadcrumb">
        <div className={tw("shell")}>
          <Link to="/">Home</Link>
          <span>/</span>
          <Link to={`/shop?category=${product.category.slug}`}>{product.category.name}</Link>
          <span>/</span>
          <strong>{product.name}</strong>
        </div>
      </nav>

      <section className={tw("product-hero")}>
        <div className={tw("shell product-hero-grid")}>
          <div className={tw("product-gallery")}>
            <div className={tw("product-thumbnails")} aria-label="Product gallery">
              {gallery.map((image, index) => (<button className={tw(activeImage === index ? 'active' : '')} type="button" key={image.src} aria-label={`Show image ${index + 1}`} aria-pressed={activeImage === index} onClick={() => setGalleryState({ productId: product.id, index })}>
                  <img src={image.src} alt=""/>
                </button>))}
            </div>
            <div className={tw(`product-main-image ${isLicenseProduct ? 'license' : ''}`)}>
              <img src={gallery[activeImage].src} alt={gallery[activeImage].alt}/>
            </div>
          </div>

          <div className={tw("product-summary")}>
            <div className={tw("product-summary-top")}>
              <span className={tw("product-badge")}>{product.is_featured ? 'FEATURED' : 'FIELD READY'}</span>
              <span className={tw("product-sku")}>SKU&nbsp;&nbsp; {product.sku}</span>
            </div>
            <h1>{product.name}</h1>
            <p className={tw("product-lead")}>
              {product.short_description || product.description}
            </p>
            <strong className={tw("product-price")}>${unitPrice.toFixed(2)}</strong>
            {product.bulk_minimum_quantity && product.bulk_unit_price ? <p className={tw(`product-bulk-price ${bulkPriceActive ? 'active' : ''}`)}>{bulkPriceActive ? `Bulk price active - $${unitPrice.toFixed(2)} each` : `Buy ${product.bulk_minimum_quantity}+ for $${Number(product.bulk_unit_price).toFixed(2)} each`}</p> : null}
            <p className={tw(`product-stock ${isOutOfStock ? 'out' : ''}`)}><span /> {isOutOfStock ? 'Currently out of stock' : isLicenseProduct ? `${product.license_term_days ?? 365}-day digital license - activates after payment approval` : `In stock - ${availableStock} ready to ship`}</p>

            <div className={tw("product-purchase-row")}>
              <div className={tw(`quantity-control ${isOutOfStock ? 'disabled' : ''}`)} aria-label="Quantity selector" aria-disabled={isOutOfStock}>
                <button type="button" aria-label="Decrease quantity" disabled={isOutOfStock || quantity <= 1} onClick={() => updateQuantity(quantity - 1)}>
                  <Minus size={17}/>
                </button>
                <strong aria-live="polite">{quantity}</strong>
                <button type="button" aria-label="Increase quantity" disabled={isOutOfStock || quantity >= maximumQuantity} onClick={() => updateQuantity(quantity + 1)}>
                  <Plus size={17}/>
                </button>
              </div>
              {isOutOfStock ? (<a className={tw("product-quote-button")} href={quoteHref}>
                  <MessageCircle size={20}/>
                  Request a quote
                </a>) : (<button className={tw("product-add-button")} type="button" onClick={() => onAdd(product, quantity)}>
                  <ShoppingBag size={20}/>
                  Add to cart
                </button>)}
            </div>
            {isOutOfStock ? null : (<button className={tw("product-buy-button")} type="button" onClick={() => onBuyNow(product, quantity)}>
                Buy now
              </button>)}

            <div className={tw("product-assurances")}>
              <button type="button" onClick={() => toast('Delivery is calculated during checkout.')}>
                <Truck size={24}/>
                <span>Delivery quote</span>
              </button>
              <button type="button" onClick={() => toast('This radio includes a 12-month warranty.')}>
                <ShieldCheck size={24}/>
                <span>12-month warranty</span>
              </button>
              <button type="button" onClick={() => toast('Secure payment options will appear at checkout.')}>
                <LockKeyhole size={24}/>
                <span>Secure payment</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {isRadio ? (<section className={tw("product-stat-band")} aria-label="Product highlights">
          <div><strong>4G LTE</strong><small>NETWORK</small></div>
          <div><strong>GLOBAL</strong><small>COVERAGE</small></div>
          <div><strong>3000 mAh</strong><small>BATTERY</small></div>
          <div><strong>FIELD</strong><small>READY</small></div>
        </section>) : null}

      {isRadio ? <section className={tw("product-features")}>
        <div className={tw("shell product-feature-grid")}>
          <div className={tw("product-feature-copy")}>
            <p className={tw("eyebrow")}>CONNECTED COMMUNICATION</p>
            <h2>Instant voice across the whole country</h2>
            <p>
              {product.name} combines instant voice communication with connected
              field workflows. {product.description || product.short_description}
            </p>
            <div className={tw("product-notice")}>
              <Info size={21}/>
              <span>A monthly subscription is required for Web Dispatch and managed talk groups.</span>
            </div>
          </div>
          <div className={tw("product-feature-list")}>
            {featureItems.map(({ icon: Icon, title, copy }) => (<div className={tw("product-feature-item")} key={title}>
                <span><Icon size={24}/></span>
                <div><strong>{title}</strong><small>{copy}</small></div>
              </div>))}
          </div>
        </div>
      </section> : (<section className={tw("product-features")}>
          <div className={tw("shell product-feature-grid")}>
            <div className={tw("product-feature-copy")}>
              <p className={tw("eyebrow")}>{isLicenseProduct ? 'RADIOADMIN SERVICE' : 'FIELD-READY ACCESSORY'}</p>
              <h2>{isLicenseProduct ? 'Annual capacity for your connected radio products' : 'Designed for dependable daily carry'}</h2>
              <p>{product.description || product.short_description}</p>
              <div className={tw("product-notice")}><Info size={21}/><span>{isLicenseProduct ? `Each license supports up to ${product.license_capacity ?? 0} compatible products and can extend an existing license or prepare capacity for future radio orders.` : 'Confirm radio fit and carry preference before placing a larger fleet order.'}</span></div>
            </div>
            <div className={tw("product-feature-list")}>
              {product.specifications.map((spec) => (<div className={tw("product-feature-item")} key={spec.key}>
                  <span><ShieldCheck size={24}/></span>
                  <div><strong>{spec.key}</strong><small>{spec.value}</small></div>
                </div>))}
            </div>
          </div>
        </section>)}

      {isRadio ? <section className={tw("product-specs")}>
        <div className={tw("shell")}>
          <p className={tw("eyebrow")}>TECHNICAL DETAILS</p>
          <h2>{product.name} specifications</h2>
          <div className={tw("product-spec-table")} role="table" aria-label={`${product.name} specifications`}>
            {detailRows.map((row) => (<div className={tw("product-spec-row")} role="row" key={row[0].key}>
                {row.map((detail) => (<Fragment key={detail.key}>
                    <span role="cell">{detail.key}</span>
                    <strong role="cell">{detail.value}</strong>
                  </Fragment>))}
              </div>))}
          </div>
          <p className={tw("product-spec-note")}>*Range depends on cellular network availability and active service.</p>
        </div>
      </section> : null}

      <section className={tw("related-products")}>
        <div className={tw("shell")}>
          <div className={tw("related-heading")}>
            <div>
              <p className={tw("eyebrow")}>COMPARE THE FLEET</p>
              <h2>More {product.category.name}</h2>
            </div>
            <Link to={`/shop?category=${product.category.slug}`}>View all {product.category.name} <ArrowUpRight size={17}/></Link>
          </div>
          {relatedProducts.length ? <div className={tw("related-grid")}>
            {relatedProducts.map((relatedProduct) => {
              const image = primaryProductImage(relatedProduct);
              return (<Link className={tw("related-card")} to={`/products/${relatedProduct.slug}`} key={relatedProduct.id}>
                <img src={mediaUrl(image?.image_url)} alt={image?.alt_text || relatedProduct.name}/>
                <span>{relatedProduct.category.name.toUpperCase()}</span>
                <h3>{relatedProduct.name}</h3>
                <strong>${Number(relatedProduct.current_price).toFixed(2)}</strong>
                <ArrowUpRight className={tw("related-arrow")} size={21}/>
              </Link>);
            })}
          </div> : <p className={tw("related-empty")}>No other products are currently available in this category.</p>}
        </div>
      </section>

      <ProductBenefits />
    </main>);
}
