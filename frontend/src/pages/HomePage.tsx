import { lazy, Suspense, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, BadgeCheck, Check, CreditCard, Headphones, MapPin, MessageSquare, Package, Plus, Radio, RadioTower, ShieldCheck, Truck } from 'lucide-react'
import { useCart } from '../contexts/CartContext'
import { api, mediaUrl, unwrap } from '../lib/api'
import { tw } from '../lib/tailwind-styles'
import { toast } from 'sonner'
import type { Banner, SiteSettings } from '../types'

const FleetVisualization = lazy(() => import('../components/FleetVisualization'));

const STORE_LINK_ALLOWED_SCHEMES = ['https:', 'mailto:', 'tel:']

function storeLinkSafeHref(href: string) {
    const value = (href ?? '').trim()
    if (!value) return null
    if (value.startsWith('#')) return value
    if (value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/\\')) return value
    try {
        const url = new URL(value, window.location.origin)
        return STORE_LINK_ALLOWED_SCHEMES.includes(url.protocol) ? value : null
    } catch {
        return null
    }
}

function StoreLink({ href, className, children }: { href: string; className: string; children: ReactNode }) {
    const safeHref = storeLinkSafeHref(href)
    if (safeHref === null) {
        return <span className={className}>{children}</span>;
    }
    if (safeHref.startsWith('/') || safeHref.startsWith('#')) {
        return <Link className={className} to={safeHref}>{children}</Link>;
    }
    return <a className={className} href={safeHref}>{children}</a>;
}

type ProductGroup = 'POC Radios' | 'Holsters';
interface Product {
    id: number;
    slug: string;
    eyebrow: string;
    name: string;
    price: number;
    image: string;
    group: ProductGroup;
}
const products: Product[] = [
    {
        id: 1,
        slug: 'iptt810-iptt820',
        eyebrow: 'POC + ANDROID HANDHELD',
        name: 'IPTT810 / IPTT820',
        price: 430,
        image: '/images/radio-810.png',
        group: 'POC Radios',
    },
    {
        id: 2,
        slug: 'iptt510',
        eyebrow: 'POC HANDHELD RADIO',
        name: 'IPTT510',
        price: 120,
        image: '/images/radio-510.png',
        group: 'POC Radios',
    },
    {
        id: 3,
        slug: 'iptt81-dual-mode',
        eyebrow: 'POC + ANALOG DUAL MODE',
        name: 'IPTT81',
        price: 340,
        image: '/images/radio-t81.png',
        group: 'POC Radios',
    },
    {
        id: 4,
        slug: 'iptt710-android',
        eyebrow: 'POC ANDROID HANDHELD',
        name: 'IPTT710',
        price: 430,
        image: '/images/radio-710.png',
        group: 'POC Radios',
    },
    {
        id: 5,
        slug: 'field-harness-carry-system',
        eyebrow: 'HANDS-FREE FIELD CARRY',
        name: 'Field Harness Carry System',
        price: 18,
        image: '/images/holsters-hero.png',
        group: 'Holsters',
    },
    {
        id: 6,
        slug: 'lightweight-chest-pack',
        eyebrow: 'LIGHTWEIGHT RADIO CARRY',
        name: 'Lightweight Chest Pack',
        price: 15,
        image: '/images/holsters-hero.png',
        group: 'Holsters',
    },
    {
        id: 7,
        slug: 'universal-shoulder-holster',
        eyebrow: 'UNIVERSAL QUICK ACCESS',
        name: 'Universal Shoulder Holster',
        price: 12,
        image: '/images/holsters-hero.png',
        group: 'Holsters',
    },
];
const categories = [
    {
        title: 'PTT over cellular',
        description: 'Nationwide coverage over 4G LTE and Wi-Fi.',
        className: 'category-blue',
        icon: RadioTower,
    },
    {
        title: 'Analog radios',
        description: 'Direct, dependable team communication.',
        className: 'category-gray',
        icon: Radio,
    },
    {
        title: 'Radio accessories',
        description: 'Antennas, headsets, holsters and more.',
        className: 'category-green',
        icon: Headphones,
    },
];
const articles = [
    {
        label: 'VHF VS UHF',
        title: 'What is VHF radio, and how is it different from UHF?',
        description: 'A practical guide to range, terrain and choosing the right band.',
        image: '/images/article-dish.png',
    },
    {
        label: "BUYER'S GUIDE",
        title: 'How to choose the right two-way radio for your needs',
        description: 'Match network, durability and audio to the way your team works.',
        image: '/images/article-guide.png',
    },
    {
        label: 'FLEET GUIDE',
        title: 'How GPS-enabled POC radios improve fleet visibility',
        description: 'See how connected teams combine instant voice with live location awareness.',
        image: '/images/article-audio.png',
    },
];
const benefits = [
  { icon: Package, title: 'Delivery', copy: 'Secure, tracked delivery' },
    { icon: BadgeCheck, title: 'Product expertise', copy: 'Help choosing the right system' },
    { icon: CreditCard, title: 'Order confirmation', copy: 'Review every detail before payment' },
    { icon: MessageSquare, title: 'Human support', copy: 'Talk to a radio specialist' },
];
function SectionHeading({ eyebrow, title, link, href, }: {
    eyebrow: string;
    title: string;
    link?: string;
    href?: string;
}) {
    return (<div className={tw("section-heading")}>
      <div>
        <p className={tw("eyebrow")}>{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      {link && href ? (<Link className={tw("text-link")} to={href}>
          {link}
          <ArrowRight size={17}/>
        </Link>) : null}
    </div>);
}
function Hero({ banner, settings }: { banner?: Banner; settings?: SiteSettings }) {
    const title = banner?.title || 'Stay connected. Wherever the work takes you.';
    const description = banner?.description || 'Professional push-to-talk radios, 4G LTE solutions and field-ready accessories, built for teams that cannot afford to lose contact.';
    const stats = settings?.homepage_hero_stats?.length ? settings.homepage_hero_stats : [
        { value: '34+', label: 'field products' },
        { value: '4', label: 'radio categories' },
        { value: 'IP68', label: 'ready options' },
    ];
    return (<section className={tw("hero")} id="top">
      <div className={tw("shell hero-grid")}>
        <div className={tw("hero-copy")}>
          <p className={tw("pill-label")}>
            <span />
            {banner?.subtitle || 'MISSION-READY COMMUNICATION'}
          </p>
          <h1>{title}</h1>
          <p className={tw("hero-description")}>{description}</p>
          <div className={tw("hero-actions")}>
            <StoreLink className={tw("button button-primary")} href={banner?.cta_url || '#products'}>
              {banner?.cta_label || 'Shop radios'}
              <ArrowRight size={18}/>
            </StoreLink>
            <StoreLink className={tw("button button-secondary")} href={settings?.homepage_hero_secondary_cta_url || '#contact'}>{settings?.homepage_hero_secondary_cta_label || 'Talk to an expert'}</StoreLink>
          </div>
          <dl className={tw("hero-stats")}>
            {stats.map((stat) => <div key={`${stat.value}-${stat.label}`}><dt>{stat.value}</dt><dd>{stat.label}</dd></div>)}
          </dl>
        </div>
        <div className={tw("hero-media")}>
          <img src={mediaUrl(banner?.image_url || '/images/hero-radio.png')} alt={banner?.title || 'Rugged professional handheld push-to-talk radio'}/>
        </div>
      </div>
    </section>);
}
function Categories() {
    return (<section className={tw("section categories-section")} id="categories">
      <div className={tw("shell")}>
        <SectionHeading eyebrow="BUILT AROUND YOUR OPERATION" title="Choose your communication layer" link="Browse all categories" href="/shop"/>
        <div className={tw("category-grid")}>
          {categories.map(({ title, description, className, icon: Icon }) => (<Link className={tw(`category-card ${className}`)} to={title === 'PTT over cellular' ? '/shop?category=poc-radios' : title === 'Radio accessories' ? '/shop?category=radio-holsters' : '/shop'} key={title}>
              <span className={tw("category-icon")}><Icon size={25}/></span>
              <span>
                <strong>{title}</strong>
                <small>{description}</small>
                <em>Explore <ArrowRight size={16}/></em>
              </span>
            </Link>))}
        </div>
      </div>
    </section>);
}
function ProductSection({ onAdd }: {
    onAdd: (product: Product) => void;
}) {
    const [activeGroup, setActiveGroup] = useState<ProductGroup>('POC Radios');
    const visibleProducts = products.filter((product) => product.group === activeGroup);
    return (<section className={tw("section products-section")} id="products">
      <div className={tw("shell")}>
        <div className={tw("product-heading")}>
          <div>
            <p className={tw("eyebrow")}>FIELD FAVORITES</p>
            <h2>Radios teams rely on</h2>
          </div>
          <div className={tw("segmented-control")} aria-label="Product category filter">
            {(['POC Radios', 'Holsters'] as ProductGroup[]).map((group) => (<button className={tw(activeGroup === group ? 'active' : '')} key={group} type="button" onClick={() => setActiveGroup(group)}>
                {group}
              </button>))}
          </div>
        </div>
        {visibleProducts.length > 0 ? (<div className={tw("product-grid")}>
            {visibleProducts.map((product) => (<article className={tw("product-card")} key={product.id}>
                <Link className={tw("product-card-link")} to={`/products/${product.slug}`} aria-label={`View ${product.name}`}/>
                <div className={tw("product-image")}>
                  <img src={product.image} alt={`${product.name} professional radio`}/>
                </div>
                <div className={tw("product-meta")}>
                  <p>{product.eyebrow}</p>
                  <h3>{product.name}</h3>
                  <strong>${product.price.toFixed(2)}</strong>
                  <button className={tw("add-button")} type="button" aria-label={`Add ${product.name} to cart`} onClick={() => onAdd(product)}>
                    <Plus size={21}/>
                  </button>
                </div>
              </article>))}
          </div>) : null}
      </div>
    </section>);
}
function Solutions({ settings }: { settings?: SiteSettings }) {
    const solutionBenefits = settings?.homepage_solution_benefits?.length ? settings.homepage_solution_benefits : [
        'Live GPS visibility between Android radios',
        'Authorized team location sharing',
        'Nationwide POC coverage',
        'Android + analog dual-mode options',
    ];
    return (<section className={tw("solutions-section")} id="solutions">
      <div className={tw("shell solutions-grid")}>
        <div className={tw("solutions-copy")}>
          <p className={tw("eyebrow lime")}>{settings?.homepage_solution_eyebrow || 'ANDROID GPS FLEET VISIBILITY'}</p>
          <h2>{settings?.homepage_solution_title || 'Push-to-talk with live team location'}</h2>
          <p>{settings?.homepage_solution_description || "GPS-enabled Android radios let authorized users see one another's live locations directly on their devices. Crews can talk, check positions and coordinate across 4G LTE without returning to dispatch."}</p>
          <ul>
            {solutionBenefits.map((item) => (<li key={item}><Check size={15}/>{item}</li>))}
          </ul>
        </div>
        <div className={tw("fleet-panel")}>
          <div className={tw("fleet-panel-head")}>
            <span><i /> ANDROID FLEET GPS</span>
            <small>5 RADIOS SHARING</small>
          </div>
          <Suspense fallback={<div className={tw("fleet-chart fleet-loading")}>Loading fleet view</div>}>
            <FleetVisualization />
          </Suspense>
          <div className={tw("fleet-visibility-note")}>
            <MapPin size={20}/>
            <span>
              <strong>Visible on every authorized Android radio</strong>
              <small>Each user can check live teammate positions from the field.</small>
            </span>
          </div>
          <div className={tw("fleet-list")}>
            <div><Truck size={18}/><span><strong>Radio A12 - Vehicle 03</strong><small>North route</small></span><em>VISIBLE</em></div>
            <div><RadioTower size={18}/><span><strong>Radio A07 - Site lead</strong><small>East worksite</small></span><em>VISIBLE</em></div>
            <div><ShieldCheck size={18}/><span><strong>Radio A19 - Security</strong><small>Main entrance</small></span><em>VISIBLE</em></div>
          </div>
        </div>
      </div>
    </section>);
}
function Comparison({ settings }: { settings?: SiteSettings }) {
    const comparisonProducts = settings?.homepage_comparison_products?.length ? settings.homepage_comparison_products : [
        { model: 'IPTT510', best_for: 'Everyday teams', network: '4G LTE POC', system: 'Dedicated radio', protection: 'Field-ready', price: '$120' },
        { model: 'IPTT81', best_for: 'Hybrid fleets', network: 'POC + Analog', system: 'Android / dual SIM', protection: 'IP68 waterproof', price: '$340' },
        { model: 'IPTT760', best_for: 'Hazardous sites', network: '4G LTE POC', system: 'ATEX-rated', protection: 'Industrial safety', price: 'Contact us' },
    ];
    const rows = [
        ['Best for', 'best_for'], ['Network', 'network'], ['System', 'system'], ['Protection', 'protection'], ['From', 'price'],
    ] as const;
    return (<section className={tw("section comparison-section")} id="comparison">
      <div className={tw("shell")}>
        <SectionHeading eyebrow={settings?.homepage_comparison_eyebrow || 'CHOOSE WITH CONFIDENCE'} title={settings?.homepage_comparison_title || 'The right radio for every role'}/>
        <div className={tw("table-scroll")}>
          <table>
            <thead>
              <tr><th>MODEL</th>{comparisonProducts.map((product) => <th key={product.model}>{product.model}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map(([label, key]) => (<tr key={label}><th>{label}</th>{comparisonProducts.map((product) => <td key={`${label}-${product.model}`}>{product[key]}</td>)}</tr>))}
            </tbody>
          </table>
        </div>
      </div>
    </section>);
}
function Benefits() {
    return (<section className={tw("benefits-section")} aria-label="Customer benefits">
      <div className={tw("shell benefit-grid")}>
        {benefits.map(({ icon: Icon, title, copy }) => (<div className={tw("benefit")} key={title}>
            <span><Icon size={22}/></span>
            <div><strong>{title}</strong><small>{copy}</small></div>
          </div>))}
      </div>
    </section>);
}
function Resources({ settings }: { settings?: SiteSettings }) {
    const resourceItems = settings?.homepage_resources?.length ? settings.homepage_resources : articles.map((article) => ({ eyebrow: article.label, title: article.title, description: article.description, image_url: article.image, url: '' }));
    return (<section className={tw("section resources-section")} id="resources">
      <div className={tw("shell")}>
        <SectionHeading eyebrow={settings?.homepage_resources_eyebrow || 'KNOWLEDGE BASE'} title={settings?.homepage_resources_title || 'Better communication starts here'}/>
        <div className={tw("article-grid")}>
          {resourceItems.map((article) => {
              const content = <><img src={mediaUrl(article.image_url)} alt=""/><span className={tw("eyebrow")}>{article.eyebrow}</span><h3>{article.title}</h3><p>{article.description}</p></>;
              return article.url ? <StoreLink className={tw("article-card")} href={article.url} key={article.title}>{content}</StoreLink> : <article className={tw("article-card")} key={article.title}>{content}</article>;
          })}
        </div>
      </div>
    </section>);
}
function ContactCta({ settings }: { settings?: SiteSettings }) {
    const contactUrl = settings?.homepage_contact_cta_url || `mailto:${settings?.support_email || 'sales@digitalptt.com'}?subject=Digital%20PTT%20product%20advice`;
    return (<section className={tw("contact-section")} id="contact">
      <div className={tw("shell")}>
        <div className={tw("contact-panel")}>
          <div>
            <p className={tw("eyebrow")}>{settings?.homepage_contact_eyebrow || 'NOT SURE WHERE TO START?'}</p>
            <h2>{settings?.homepage_contact_title || "Tell us how your team works. We'll match the right system."}</h2>
            <p>{settings?.homepage_contact_description || 'From a single radio to a connected fleet, get practical guidance before you buy.'}</p>
          </div>
          <StoreLink className={tw("button button-white")} href={contactUrl}>
            {settings?.homepage_contact_cta_label || 'Contact a specialist'}
            <ArrowRight size={18}/>
          </StoreLink>
        </div>
      </div>
    </section>);
}
export function HomePage() {
    const cart = useCart();
    const bannersQuery = useQuery({ queryKey: ['banners'], queryFn: api.banners });
    const settingsQuery = useQuery({ queryKey: ['site-settings'], queryFn: api.siteSettings });
    const banner = bannersQuery.data ? unwrap(bannersQuery.data).find((item) => item.is_active) : undefined;
    const addToCart = (product: Product) => {
        api.product(product.slug)
            .then((liveProduct) => cart.add(liveProduct))
            .catch(() => toast.error('This product could not be verified. Please try again.'));
    };
    return (<main>
      <Hero banner={banner} settings={settingsQuery.data} />
      <Categories />
      <ProductSection onAdd={addToCart}/>
      <Solutions settings={settingsQuery.data} />
      <Comparison settings={settingsQuery.data} />
      <Benefits />
      <Resources settings={settingsQuery.data} />
      <ContactCta settings={settingsQuery.data} />
    </main>);
}
