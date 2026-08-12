import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LayoutDashboard, LogIn, LogOut, Menu, RadioTower, Search, ShoppingBag, UserPlus, UserRound, X } from 'lucide-react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { NotificationMenu } from '../components/NotificationMenu'
import { useAuth } from '../contexts/AuthContext'
import { useCart } from '../contexts/CartContext'
import { api } from '../lib/api'
import { tw } from '../lib/tailwind-styles'
import type { User } from '../types'

function Logo({ siteName = 'Digital PTT' }: { siteName?: string }) {
    return (<Link className={tw("brand")} to="/" aria-label="Digital PTT home">
      <span className={tw("brand-mark")}>
        <RadioTower size={22} strokeWidth={2.2}/>
      </span>
      <span>{siteName}</span>
    </Link>);
}
function Header({ cartCount, siteName, user, authReady, onLogout }: {
    cartCount: number;
    siteName?: string;
    user: User | null;
    authReady: boolean;
    onLogout: () => Promise<void>;
}) {
    const [menuOpen, setMenuOpen] = useState(false);
    const [searchOpen, setSearchOpen] = useState(false);
    const [accountOpen, setAccountOpen] = useState(false);
    const accountMenuRef = useRef<HTMLDivElement>(null);
    const location = useLocation();
    const navigate = useNavigate();
    const isProductPage = location.pathname.startsWith('/products/');
    const isCommercePage = isProductPage || location.pathname === '/cart' || location.pathname === '/checkout' || location.pathname === '/payment' || location.pathname === '/payment-preview';
    useEffect(() => {
        if (!accountOpen)
            return;
        const closeOnOutsideClick = (event: MouseEvent) => {
            if (!accountMenuRef.current?.contains(event.target as Node))
                setAccountOpen(false);
        };
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape')
                setAccountOpen(false);
        };
        document.addEventListener('mousedown', closeOnOutsideClick);
        document.addEventListener('keydown', closeOnEscape);
        return () => {
            document.removeEventListener('mousedown', closeOnOutsideClick);
            document.removeEventListener('keydown', closeOnEscape);
        };
    }, [accountOpen]);
    const logout = async () => {
        setAccountOpen(false);
        setMenuOpen(false);
        await onLogout();
        navigate('/');
    };
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
            <Link to="/shop" onClick={() => setMenuOpen(false)}>Shop</Link>
            <Link to="/shop?category=poc-radios" onClick={() => setMenuOpen(false)}>POC Radios</Link>
            <Link to="/shop?category=radio-holsters" onClick={() => setMenuOpen(false)}>Accessories</Link>
            <Link to="/#solutions" onClick={() => setMenuOpen(false)}>
              {isCommercePage ? 'Solutions by industry' : 'Solutions'}
            </Link>
            <Link to="/#resources" onClick={() => setMenuOpen(false)}>
              {isCommercePage ? 'Guides & support' : 'Resources'}
            </Link>
            {user ? <>
              {user.is_staff ? <Link className={tw("mobile-account-action")} to="/admin" onClick={() => setMenuOpen(false)}><LayoutDashboard size={18}/>Dashboard</Link> : null}
              <Link className={tw("mobile-account-action")} to="/account" onClick={() => setMenuOpen(false)}><UserRound size={18}/>My account</Link>
              <button className={tw("mobile-account-action danger")} type="button" onClick={logout}><LogOut size={18}/>Log out</button>
            </> : <>
              <Link className={tw("mobile-account-action")} to="/login" onClick={() => setMenuOpen(false)}><LogIn size={18}/>Sign in</Link>
              <Link className={tw("mobile-account-action")} to="/register" onClick={() => setMenuOpen(false)}><UserPlus size={18}/>Create account</Link>
            </>}
          </nav>
          <div className={tw("nav-actions")}>
            <button className={tw("icon-button")} type="button" aria-label="Search" aria-expanded={searchOpen} onClick={() => setSearchOpen((open) => !open)}>
              <Search size={21}/>
            </button>
            {user ? <NotificationMenu userId={user.id} variant="public" /> : null}
            <div className={tw("account-menu-wrap desktop-action")} ref={accountMenuRef}>
              <button className={tw("icon-button")} type="button" aria-label={user ? 'Open profile menu' : 'Open sign in menu'} aria-haspopup="menu" aria-expanded={accountOpen} disabled={!authReady} onClick={() => setAccountOpen((open) => !open)}>
                <UserRound size={21}/>
              </button>
              {accountOpen ? <div className={tw("account-menu")} role="menu">
                {user ? <>
                  <div className={tw("account-menu-head")}>
                    <span>{`${user.first_name[0] ?? ''}${user.last_name[0] ?? ''}` || user.email[0].toUpperCase()}</span>
                    <div><strong>{`${user.first_name} ${user.last_name}`.trim() || 'My account'}</strong><small>{user.email}</small></div>
                  </div>
                  {user.is_staff ? <Link className={tw("account-menu-link")} role="menuitem" to="/admin" onClick={() => setAccountOpen(false)}><LayoutDashboard size={17}/>Dashboard</Link> : null}
                  <Link className={tw("account-menu-link")} role="menuitem" to="/account" onClick={() => setAccountOpen(false)}><UserRound size={17}/>View profile</Link>
                  <button className={tw("account-menu-link account-menu-danger")} role="menuitem" type="button" onClick={logout}><LogOut size={17}/>Log out</button>
                </> : <>
                  <div className={tw("account-menu-copy")}><strong>Your account</strong><small>Sign in to view quotes and profile details.</small></div>
                  <Link className={tw("account-menu-link")} role="menuitem" to="/login" onClick={() => setAccountOpen(false)}><LogIn size={17}/>Sign in</Link>
                  <Link className={tw("account-menu-link")} role="menuitem" to="/register" onClick={() => setAccountOpen(false)}><UserPlus size={17}/>Create account</Link>
                </>}
              </div> : null}
            </div>
            <Link className={tw("icon-button cart-button")} to="/cart" aria-label={`Open cart with ${cartCount} items`}>
              <ShoppingBag size={21}/>
              {cartCount > 0 ? <span className={tw("cart-count")}>{cartCount}</span> : null}
            </Link>
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
          <div><strong>Explore</strong><Link to="/#solutions">Fleet solutions</Link><Link to="/#comparison">Compare radios</Link><Link to="/#resources">Radio guides</Link><a href={`mailto:${supportEmail || 'sales@digitalptt.com'}`}>Contact a specialist</a></div>
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
  const auth = useAuth()
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
      {isAuthRoute ? null : <Header cartCount={cart.count} siteName={settings?.site_name} user={auth.user} authReady={auth.ready} onLogout={auth.logout} />}
      <Outlet />
      {isAuthRoute ? null : <Footer siteName={settings?.site_name} tagline={settings?.tagline} supportEmail={settings?.support_email} />}
    </>
  )
}
