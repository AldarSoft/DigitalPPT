import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Box, CreditCard, FileText, KeyRound, LayoutDashboard, LogOut, Menu, PanelsTopLeft, Search, Settings, ShoppingCart, Users, Warehouse, X } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { NotificationMenu } from '../components/NotificationMenu'
import { OverflowTooltipText } from '../components/OverflowTooltipText'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../lib/api'
import { tw } from '../lib/tailwind-styles'

export function AdminLayout() {
    const auth = useAuth();
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);
    const adminName = `${auth.user?.first_name ?? ''} ${auth.user?.last_name ?? ''}`.trim() || 'Administrator';
    const permissions = auth.user?.staff_permissions ?? [];
    const isSuperAdministrator = (auth.user?.staff_roles ?? []).includes('Super Administrator');
    const can = (...required: string[]) => required.some((permission) => permissions.includes(permission));
    const quoteCountQuery = useQuery({
        queryKey: ['admin-quotes', 'sidebar-count'],
        queryFn: () => api.quotes('status=new&page=1&page_size=1'),
        enabled: can('manage_quotes', 'confirm_bank_payments'),
    });
    const orderCountQuery = useQuery({
        queryKey: ['admin-orders', 'sidebar-count'],
        queryFn: () => api.orders('status=pending&page=1&page_size=1'),
        enabled: can('manage_orders'),
    });
    const badgeCounts = {
        quotes: resultCount(quoteCountQuery.data),
        orders: resultCount(orderCountQuery.data),
    };
    const links = [
        ['/admin', LayoutDashboard, 'Overview', true, null, isSuperAdministrator],
        ['/admin/products', Box, 'Products', false, null, can('manage_inventory')],
        ['/admin/quotes', FileText, 'Quotes', false, 'quotes', can('manage_quotes', 'confirm_bank_payments')],
        ['/admin/orders', ShoppingCart, 'Orders', false, 'orders', can('manage_orders')],
        ['/admin/payments', CreditCard, 'Payments', false, null, can('manage_payment_settings', 'confirm_bank_payments')],
        ['/admin/customers', Users, 'Customers', false, null, can('manage_users')],
        ['/admin/licenses', KeyRound, 'License Management', false, null, can('manage_licenses')],
        ['/admin/inventory', Warehouse, 'Inventory', false, null, can('manage_inventory')],
    ].filter((item) => item[5]) as Array<[string, typeof LayoutDashboard, string, boolean, 'quotes' | 'orders' | null, boolean]>;
    return (<div className={tw("admin-shell")}>
      <aside className={tw(`admin-sidebar ${open ? 'open' : ''}`)}>
        <NavLink className={tw("admin-brand")} to="/" aria-label="Digital PTT home"><img src="/digital-ptt-logo.svg" alt="Digital PTT" /></NavLink>
        <button className={tw("admin-close")} type="button" aria-label="Close menu" onClick={() => setOpen(false)}><X /></button>
        <p>OPERATIONS</p>
        <nav>
          {links.map(([to, Icon, label, end, badge]) => {
            const count = badge ? badgeCounts[badge] : 0;
            return <NavLink end={end} to={to} key={to} onClick={() => setOpen(false)}><Icon size={20}/>{label}{count > 0 ? <strong className="ml-auto inline-flex min-w-5 items-center justify-center rounded-full bg-danger px-1.5 text-[10px] font-extrabold leading-5 text-white" aria-label={`${count} ${label.toLowerCase()} waiting`}>{count > 99 ? '99+' : count}</strong> : null}</NavLink>;
          })}
          <span>INSIGHTS</span>
          {isSuperAdministrator ? <NavLink to="/admin/analytics" onClick={() => setOpen(false)}><BarChart3 size={20}/>Analytics</NavLink> : null}
          {can('manage_site_settings') ? <NavLink to="/admin/site-settings" onClick={() => setOpen(false)}><PanelsTopLeft size={20}/>Site settings</NavLink> : null}
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
          {can('manage_inventory') ? <div><Search size={19}/><input placeholder="Search products" onKeyDown={(event) => {
            if (event.key === 'Enter')
                navigate(`/admin/products?search=${encodeURIComponent(event.currentTarget.value)}`);
        }}/></div> : <span />}
          {auth.user ? <NotificationMenu userId={auth.user.id} variant="admin" /> : null}
        </header>
        <Outlet />
      </div>
    </div>);
}

function resultCount(value: { count: number } | unknown[] | undefined) {
    if (!value) return 0;
    return Array.isArray(value) ? value.length : value.count;
}
