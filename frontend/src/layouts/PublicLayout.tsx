import { useEffect, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Menu, RadioTower, Search, ShoppingBag, UserRound, X } from 'lucide-react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useCart } from '../contexts/CartContext'
import { api } from '../lib/api'
import { tw } from '../lib/tailwind-styles'

function Logo({ siteName = 'Digital PTT' }: { siteName?: string }) {
    return (<Link className={tw("brand")} to="/" aria-label="Digital PTT home">
      <span className={tw("brand-mark")}>
        <RadioTower size={22} strokeWidth={2.2}/>
      </span>
      <span>{siteName}</span>
    </Link>);
}
function Header({ cartCount, siteName }: {
    cartCount: number;
    siteName?: string;
}) {
    const [menuOpen, setMenuOpen] = useState(false);
    const [searchOpen, setSearchOpen] = useState(false);
    const location = useLocation();
    const navigate = useNavigate();
    const isProductPage = location.pathname.startsWith('/products/');
    const isCommercePage = isProductPage || location.pathname === '/cart' || location.pathname === '/checkout';
    const submitSearch = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const term = String(form.get('search') ?? '').trim();
        if (!term)
            return;
        setSearchOpen(false);
        navigate(`/shop?search=${encodeURIComponent(term)}`);
    };
    return (<>
      <div className={tw("announcement")}>
        <span>{isCommercePage ? 'FIELD-READY GEAR' : 'GLOBAL RADIO SOLUTIONS'}</span>
        <i />
        <span>QUOTE SUPPORT</span>
        <i />
        <span>EXPERT SUPPORT</span>
      </div>
      <header className={tw("site-header")}>
        <div className={tw("shell nav-shell")}>
          <Logo siteName={siteName} />
          <nav className={tw(`main-nav ${menuOpen ? 'is-open' : ''}`)} aria-label="Main navigation">
            <a href="/shop" onClick={() => setMenuOpen(false)}>Shop</a>
            <a href="/shop?category=poc-radios" onClick={() => setMenuOpen(false)}>POC Radios</a>
            <a href="/shop?category=radio-holsters" onClick={() => setMenuOpen(false)}>Accessories</a>
            <a href="/#solutions" onClick={() => setMenuOpen(false)}>
              {isCommercePage ? 'Solutions by industry' : 'Solutions'}
            </a>
            <a href="/#resources" onClick={() => setMenuOpen(false)}>
              {isCommercePage ? 'Guides & support' : 'Resources'}
            </a>
          </nav>
          <div className={tw("nav-actions")}>
            <button className={tw("icon-button")} type="button" aria-label="Search" aria-expanded={searchOpen} onClick={() => setSearchOpen((open) => !open)}>
              <Search size={21}/>
            </button>
            <a className={tw("icon-button desktop-action")} href="/account" aria-label="Account">
              <UserRound size={21}/>
            </a>
            <a className={tw("icon-button cart-button")} href="/cart" aria-label={`Open cart with ${cartCount} items`}>
              <ShoppingBag size={21}/>
              {cartCount > 0 ? <span className={tw("cart-count")}>{cartCount}</span> : null}
            </a>
            <button className={tw("icon-button menu-button")} type="button" aria-label={menuOpen ? 'Close menu' : 'Open menu'} onClick={() => setMenuOpen((open) => !open)}>
              {menuOpen ? <X size={22}/> : <Menu size={22}/>}
            </button>
          </div>
        </div>
        {searchOpen ? (<form className={tw("search-bar shell")} onSubmit={submitSearch}>
            <Search size={20} aria-hidden="true"/>
            <input autoFocus name="search" type="search" placeholder="Search radios, accessories and guides" aria-label="Search catalog"/>
            <button type="submit">Search</button>
          </form>) : null}
      </header>
    </>);
}
function Footer({ siteName, tagline, supportEmail }: { siteName?: string; tagline?: string; supportEmail?: string }) {
    return (<footer className={tw("site-footer")}>
      <div className={tw("shell footer-grid")}>
        <div className={tw("footer-brand")}>
          <Logo siteName={siteName} />
          <p>{tagline || 'Your communication solutions, professional radios, connected systems and field-ready accessories.'}</p>
        </div>
        <div className={tw("footer-links")}>
          <div><strong>Shop</strong><Link to="/shop?category=poc-radios">POC radios</Link><Link to="/shop?category=radio-holsters">Radio holsters</Link><Link to="/shop?stock=true">In-stock products</Link><Link to="/shop">All products</Link></div>
          <div><strong>Explore</strong><a href="/#solutions">Fleet solutions</a><a href="/#comparison">Compare radios</a><a href="/#resources">Radio guides</a><a href={`mailto:${supportEmail || 'sales@digitalptt.com'}`}>Contact a specialist</a></div>
          <div><strong>Account</strong><Link to="/account">My account</Link><Link to="/cart">Cart</Link><Link to="/login">Sign in</Link><Link to="/register">Create account</Link></div>
        </div>
      </div>
      <div className={tw("footer-bottom")}>
        <div className={tw("shell")}><span>&copy; 2026 {siteName || 'Digital PTT'}. All rights reserved.</span><span>SECURE QUOTE REQUESTS&nbsp;&nbsp; &middot; &nbsp;&nbsp;GLOBAL SUPPORT</span></div>
      </div>
    </footer>);
}

export function PublicLayout() {
  const cart = useCart()
  const location = useLocation()
  const settingsQuery = useQuery({ queryKey: ['site-settings'], queryFn: api.siteSettings })
  const settings = settingsQuery.data
  const isAuthRoute = location.pathname === '/login' || location.pathname === '/register'

  useEffect(() => {
    document.title = settings?.meta_title || settings?.site_name || 'Digital PTT'
    const meta = document.querySelector<HTMLMetaElement>('meta[name="description"]')
    if (meta && settings?.meta_description) meta.content = settings.meta_description
  }, [settings?.meta_description, settings?.meta_title, settings?.site_name])

  return (
    <>
      {isAuthRoute ? null : <Header cartCount={cart.count} siteName={settings?.site_name} />}
      <Outlet />
      {isAuthRoute ? null : <Footer siteName={settings?.site_name} tagline={settings?.tagline} supportEmail={settings?.support_email} />}
    </>
  )
}
