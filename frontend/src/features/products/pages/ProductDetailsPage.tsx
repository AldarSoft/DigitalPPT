import { tw } from "../../../lib/tailwind-styles";
import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowUpRight, CreditCard, FileText, MessageCircle, Minus, PackageCheck, Plus, ShieldCheck, ShoppingBag, } from 'lucide-react';
import { useCart } from '../../../contexts/CartContext';
import { api, ApiError, mediaUrl, unwrap } from '../../../lib/api';
import { productRequestState } from '../../../lib/catalog-request-state';
import { unitPriceForQuantity } from '../../../lib/pricing';
import type { Product } from '../../../types';
import { ProductAssurances, ProductMarketing } from '../components/ProductContent';
import { visibleAssurances } from '../../../lib/product-presentation';
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
export function ProductDetailsPage({ preview = false }: { preview?: boolean }) {
    const cart = useCart();
    const navigate = useNavigate();
    const onAdd = (product: Product, quantity: number) => cart.add(product, quantity);
    const onBuyNow = (product: Product, quantity: number) => {
        cart.add(product, quantity);
        navigate('/cart');
    };
    const { slug = 'iptt510' } = useParams();
    const productQuery = useQuery({
        queryKey: [preview ? 'product-preview' : 'product', slug],
        queryFn: () => preview ? api.previewProduct(slug) : api.product(slug),
        retry: (failureCount, error) => !(error instanceof ApiError && error.status === 404) && failureCount < 2,
    });
    const paymentStatus = useQuery({ queryKey: ['storefront-payment-status'], queryFn: api.storefrontPaymentStatus });
    const product = productQuery.isError ? undefined : productQuery.data;
    const requestState = productRequestState({
        hasData: Boolean(product),
        isLoading: productQuery.isLoading,
        status: productQuery.error instanceof ApiError ? productQuery.error.status : undefined,
    });
    const [galleryState, setGalleryState] = useState({ productId: 0, index: 0 });
    const relatedQuery = useQuery({
        queryKey: ['related-products', product?.category.slug],
        queryFn: () => api.products(`category=${encodeURIComponent(product?.category.slug ?? '')}`),
        enabled: Boolean(product),
    });
    const [quantityState, setQuantityState] = useState({ productId: 0, value: 1 });
    if (!product) {
        const notFound = requestState === 'not-found';
        return (<main className={tw("route-message shell")}>
          {notFound ? <MessageCircle size={32}/> : <AlertTriangle size={32}/>}
          <h1>{requestState === 'loading' ? 'Loading product...' : notFound ? 'Product not found' : 'Product temporarily unavailable'}</h1>
          <p>{requestState === 'loading' ? 'Fetching the latest product information.' : notFound ? 'This product may have been removed or its address may have changed.' : 'We could not verify this product, price, or availability. Please try again.'}</p>
          {requestState === 'loading' ? null : notFound ? <Link className={tw("primary-action")} to="/shop">Browse the catalog <ArrowUpRight size={17}/></Link> : <button className={tw("primary-action")} type="button" onClick={() => void productQuery.refetch()}>Try again</button>}
        </main>);
    }
    const isLicenseProduct = product.licensing_role === 'license_product';
    const isCoveragePlan = isLicenseProduct && product.license_billing_model === 'per_radio';
    const availableStock = Math.max(0, product.inventory_quantity);
    const maximumQuantity = product.is_stock_tracked === false ? 1000 : availableStock;
    const isOutOfStock = product.is_stock_tracked !== false && availableStock === 0;
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
    const isRadio = product.detail_layout === 'radio';
    const quoteHref = `mailto:sales@digitalptt.com?subject=${encodeURIComponent(`Quote request: ${product.name}`)}&body=${encodeURIComponent(`Hello, I would like a quote for ${product.name} (SKU: ${product.sku}).`)}`;
    const relatedProducts = (relatedQuery.data ? unwrap(relatedQuery.data) : [])
        .filter((item) => item.category.slug === product.category.slug && item.id !== product.id)
        .slice(0, 3);
    const detailItems = [
        { key: 'Model', value: product.name },
        { key: 'SKU', value: product.sku },
        { key: 'Brand', value: product.brand },
        { key: 'Category', value: product.category.name },
        ...product.specifications,
    ];
    const highlightItems = product.specifications.filter((item) => item.show_in_highlights).slice(0, 4);
    const highlightColumns = {
        1: 'grid-cols-1',
        2: 'grid-cols-2',
        3: 'grid-cols-3 max-[760px]:grid-cols-2',
        4: 'grid-cols-4 max-[760px]:grid-cols-2',
    }[highlightItems.length];
    const detailRows = Array.from({ length: Math.ceil(detailItems.length / 2) }, (_, index) => detailItems.slice(index * 2, index * 2 + 2));
    return (<main className={tw("product-page")}>
      {preview ? <div className="border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm">Product preview · {product.status} <Link className="ml-4 underline" to="/admin/products">Back to products</Link></div> : null}
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
            <p className={tw(`product-stock ${isOutOfStock ? 'out' : ''}`)}><span /> {isOutOfStock ? 'Currently out of stock' : isCoveragePlan ? `${product.license_term_days ?? 365}-day radio coverage - activates after quoted payment is confirmed` : isLicenseProduct ? `${product.license_term_days ?? 365}-day digital license - activates after payment approval` : `In stock - ${availableStock} ready to ship`}</p>

            {isCoveragePlan ? <div className="mt-6" inert={preview}><Link className={`${tw("product-quote-button")} min-h-[58px] w-full`} to={`/products/${product.slug}/coverage`}><FileText size={20}/>Request coverage quote</Link><p className="mt-3 text-sm leading-relaxed text-muted">Sign in to select uncovered radios from your organization. No payment is collected when you submit the request.</p></div> : <div className={tw("product-purchase-row")} inert={preview}>
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
            </div>}
            {isCoveragePlan || isOutOfStock || preview ? null : (<button className={tw("product-buy-button")} type="button" onClick={() => onBuyNow(product, quantity)}>
                Buy now
              </button>)}

            <ProductAssurances items={visibleAssurances(product.presentation.assurances, paymentStatus.data)} />
          </div>
        </div>
      </section>

      {highlightItems.length ? (<section className={tw("product-stat-band", highlightColumns)} aria-label="Product highlights">
          {highlightItems.map((item) => <div key={`${item.key}-${item.sort_order}`}><strong>{item.value}</strong><small>{item.key.toUpperCase()}</small></div>)}
        </section>) : null}

      <ProductMarketing content={product.presentation} description={product.description || product.short_description} />

      {detailItems.length ? <section className={tw("product-specs")}>
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
          {isRadio ? <p className={tw("product-spec-note")}>*Range depends on cellular network availability and active service.</p> : null}
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
