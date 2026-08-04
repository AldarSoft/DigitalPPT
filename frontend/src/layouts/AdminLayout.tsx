import { useState } from 'react'
import { BarChart3, Bell, Box, FileText, LayoutDashboard, LogOut, Menu, PanelsTopLeft, RadioTower, Search, Settings, ShoppingCart, Tag, Users, Warehouse, X } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { OverflowTooltipText } from '../components/OverflowTooltipText'
import { useAuth } from '../contexts/AuthContext'
import { tw } from '../lib/tailwind-styles'

export function AdminLayout() {
    const auth = useAuth();
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);
    const adminName = `${auth.user?.first_name ?? ''} ${auth.user?.last_name ?? ''}`.trim() || 'Administrator';
    const links = [
        ['/admin', LayoutDashboard, 'Overview', true],
        ['/admin/products', Box, 'Products', false],
        ['/admin/quotes', FileText, 'Quotes', false],
        ['/admin/orders', ShoppingCart, 'Orders', false],
        ['/admin/customers', Users, 'Customers', false],
        ['/admin/promotions', Tag, 'Promotions', false],
        ['/admin/inventory', Warehouse, 'Inventory', false],
    ] as const;
    return (<div className={tw("admin-shell")}>
      <aside className={tw(`admin-sidebar ${open ? 'open' : ''}`)}>
        <NavLink className={tw("admin-brand")} to="/"><span><RadioTower size={21}/></span>Digital PTT</NavLink>
        <button className={tw("admin-close")} type="button" aria-label="Close menu" onClick={() => setOpen(false)}><X /></button>
        <p>OPERATIONS</p>
        <nav>
          {links.map(([to, Icon, label, end]) => (<NavLink end={end} to={to} key={to} onClick={() => setOpen(false)}><Icon size={20}/>{label}</NavLink>))}
          <span>INSIGHTS</span>
          <NavLink to="/admin/analytics" onClick={() => setOpen(false)}><BarChart3 size={20}/>Analytics</NavLink>
          <NavLink to="/admin/site-settings" onClick={() => setOpen(false)}><PanelsTopLeft size={20}/>Site settings</NavLink>
          <NavLink to="/account"><Settings size={20}/>Account settings</NavLink>
        </nav>
        <div className={tw("admin-user")}>
          <span>{`${auth.user?.first_name[0] ?? ''}${auth.user?.last_name[0] ?? ''}` || 'AD'}</span>
          <div><OverflowTooltipText as="strong" text={adminName}/><OverflowTooltipText as="small" text={auth.user?.email || 'Administrator'}/></div>
          <button type="button" aria-label="Log out" onClick={async () => { await auth.logout(); navigate('/login'); }}><LogOut size={18}/></button>
        </div>
      </aside>
      <div className={tw("admin-main")}>
        <header className={tw("admin-topbar")}>
          <button className={tw("admin-menu")} type="button" aria-label="Open menu" onClick={() => setOpen(true)}><Menu size={21}/></button>
          <div><Search size={19}/><input placeholder="Search quotes, orders, products" onKeyDown={(event) => {
            if (event.key === 'Enter')
                navigate(`/admin/products?search=${encodeURIComponent(event.currentTarget.value)}`);
        }}/></div>
          <button type="button" aria-label="Notifications"><Bell size={20}/></button>
        </header>
        <Outlet />
      </div>
    </div>);
}
