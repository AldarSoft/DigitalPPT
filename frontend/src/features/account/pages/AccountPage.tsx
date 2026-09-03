import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Building2, CreditCard, FileText, KeyRound, LayoutDashboard, LogOut, Menu, Package, Settings, UserRound, Users, X, type LucideIcon } from 'lucide-react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { OverflowTooltipText } from '../../../components/OverflowTooltipText'
import { Pagination } from '../../../components/Pagination'
import { useAuth } from '../../../contexts/AuthContext'
import { api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { User } from '../../../types'
import { AccountOverview } from '../components/AccountOverview'
import { AccountRecordDialog, type AccountRecord } from '../components/AccountRecordDialog'
import { OrdersTable } from '../components/OrdersTable'
import { ProfileForm } from '../components/ProfileForm'
import { QuotesTable } from '../components/QuotesTable'
import type { AccountTab } from '../types'
import { OrganizationLicensesPanel } from '../../licensing/pages/OrganizationLicensesPanel'
import { OrganizationTeamPanel } from '../../licensing/pages/OrganizationTeamPanel'
import { OrganizationSettingsPanel } from '../../licensing/pages/OrganizationSettingsPanel'
import { licensingKeys } from '../../licensing/queryKeys'

const ORDER_PAGE_SIZE = 8
const QUOTE_PAGE_SIZE = 10
const ACCOUNT_TABS: AccountTab[] = ['overview', 'quotes', 'orders', 'licenses', 'team', 'organization', 'settings']
const STAFF_ACCOUNT_TABS: AccountTab[] = ['settings']
type AccountNavItem = readonly [AccountTab, LucideIcon, string]
const ACCOUNT_NAV_ITEMS: AccountNavItem[] = [
  ['overview', LayoutDashboard, 'Overview'],
  ['quotes', FileText, 'Quote requests'],
  ['orders', Package, 'Orders'],
  ['licenses', KeyRound, 'Licenses'],
  ['team', Users, 'Organization Team'],
  ['organization', Building2, 'Organization settings'],
  ['settings', Settings, 'Account settings'],
]
const STAFF_ACCOUNT_NAV_ITEMS: AccountNavItem[] = [
  ['settings', Settings, 'Account settings'],
]

export function AccountPage() {
  const auth = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab') as AccountTab | null;
  const linkedQuoteNumber = searchParams.get('quote');
  const requestedOrganizationId = Number(searchParams.get('org')) || null;
  const isStaff = Boolean(auth.user?.is_staff);
  const availableTabs = isStaff ? STAFF_ACCOUNT_TABS : ACCOUNT_TABS;
  const requestedAccountTab: AccountTab = requestedTab && availableTabs.includes(requestedTab) ? requestedTab : isStaff ? 'settings' : 'overview';
  const [orderPage, setOrderPage] = useState(1);
  const [quotePage, setQuotePage] = useState(1);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [selectedRecordState, setSelectedRecordState] = useState<AccountRecord | null>(null);
  const workspacesQuery = useQuery({
    queryKey: ['licensing', 'organization', 'workspaces'],
    queryFn: api.organizationWorkspaces,
    enabled: Boolean(auth.user && !isStaff),
    staleTime: 0,
    refetchOnMount: 'always',
  });
  const requestedOrganizationIsAvailable = Boolean(
    requestedOrganizationId
    && workspacesQuery.data?.organizations.some((organization) => organization.id === requestedOrganizationId),
  );
  const organizationId = requestedOrganizationIsAvailable
    ? requestedOrganizationId
    : workspacesQuery.data?.default_organization_id ?? null;
  const selectedOrganization = workspacesQuery.data?.organizations.find((organization) => organization.id === organizationId) ?? null;
  const hasNoOrganization = Boolean(!isStaff && workspacesQuery.isSuccess && workspacesQuery.data.organizations.length === 0);
  const tab: AccountTab = hasNoOrganization && (requestedAccountTab === 'team' || requestedAccountTab === 'organization')
    ? 'licenses'
    : requestedAccountTab;
  const accountNavItems = hasNoOrganization
    ? ACCOUNT_NAV_ITEMS.filter(([value]) => value !== 'team' && value !== 'organization')
    : ACCOUNT_NAV_ITEMS;
  useEffect(() => {
    if (isStaff || !workspacesQuery.data) return;
    const next = new URLSearchParams(searchParams);
    if (organizationId) {
      if (requestedOrganizationId === organizationId) return;
      next.set('org', String(organizationId));
    } else {
      if (!requestedOrganizationId) return;
      next.delete('org');
      next.delete('license');
    }
    setSearchParams(next, { replace: true });
  }, [isStaff, organizationId, requestedOrganizationId, searchParams, setSearchParams, workspacesQuery.data]);
  useEffect(() => {
    if (!hasNoOrganization || (requestedTab !== 'team' && requestedTab !== 'organization')) return;
    const next = new URLSearchParams(searchParams);
    next.set('tab', 'licenses');
    next.delete('org');
    setSearchParams(next, { replace: true });
  }, [hasNoOrganization, requestedTab, searchParams, setSearchParams]);
  const ordersQuery = useQuery({
    queryKey: ["orders", "mine", organizationId, orderPage],
    queryFn: () => api.orders(`ordering=-created_at&page=${orderPage}&page_size=${ORDER_PAGE_SIZE}${organizationId ? `&organization=${organizationId}` : ''}`),
    enabled: Boolean(auth.user && !isStaff),
    placeholderData: (previous) => previous,
  });
  const quotesQuery = useQuery({
    queryKey: ['quotes', 'mine', quotePage],
    queryFn: () => api.quotes(`ordering=-created_at&page=${quotePage}&page_size=${QUOTE_PAGE_SIZE}`),
    enabled: Boolean(auth.user && !isStaff),
    staleTime: 0,
    refetchOnMount: 'always',
    placeholderData: (previous) => previous,
  });
  const linkedQuoteQuery = useQuery({
    queryKey: ['quotes', 'mine', 'detail', linkedQuoteNumber],
    queryFn: () => api.quote(linkedQuoteNumber!),
    enabled: Boolean(auth.user && !isStaff && linkedQuoteNumber),
  });
  const paymentStatusQuery = useQuery({
    queryKey: ['storefront-payment-status'],
    queryFn: api.storefrontPaymentStatus,
    enabled: Boolean(auth.user && !isStaff),
  });
  const organizationSummaryQuery = useQuery({
    queryKey: licensingKeys.summary(organizationId),
    queryFn: () => api.organizationSummary(organizationId),
    enabled: Boolean(auth.user && !isStaff && organizationId),
    staleTime: 0,
    refetchOnMount: 'always',
  });
  if (!auth.ready)
    return <main className={tw("route-loading")}>Loading account...</main>;
  if (!auth.user)
    return <Navigate to="/login" state={{ from: "/account" }} replace />;
  const orders = ordersQuery.data ? unwrap(ordersQuery.data) : [];
  const quotes = quotesQuery.data ? unwrap(quotesQuery.data) : [];
  const pendingInvoiceQuote = quotes.find((quote) => (
    ['invoice_sent', 'awaiting_payment', 'payment_rejected'].includes(quote.status)
    && quote.order_status === 'pending'
  ));
  const selectedRecord = selectedRecordState ?? (linkedQuoteQuery.data ? { kind: 'quote' as const, value: linkedQuoteQuery.data } : null);
  const orderCount = ordersQuery.data && !Array.isArray(ordersQuery.data) ? ordersQuery.data.count : orders.length;
  const quoteCount = quotesQuery.data && !Array.isArray(quotesQuery.data) ? quotesQuery.data.count : quotes.length;
  const name =
    `${auth.user.first_name} ${auth.user.last_name}`.trim() || auth.user.email;
  const selectTab = (nextTab: AccountTab) => {
    setAccountMenuOpen(false);
    if (nextTab === 'overview') {
      setOrderPage(1);
      setQuotePage(1);
    }
    const next = new URLSearchParams();
    if (nextTab !== 'overview') next.set('tab', nextTab);
    if (organizationId) next.set('org', String(organizationId));
    setSearchParams(next, { replace: true });
  };
  const selectQuote = (quote: AccountRecord & { kind: 'quote' }) => {
    setSelectedRecordState(quote);
    const next = new URLSearchParams({ tab: 'quotes', quote: quote.value.quote_number });
    if (organizationId) next.set('org', String(organizationId));
    setSearchParams(next, { replace: true });
  };
  const closeRecord = () => {
    setSelectedRecordState(null);
    if (!linkedQuoteNumber) return;
    const next = new URLSearchParams(searchParams);
    next.delete('quote');
    setSearchParams(next, { replace: true });
  };
  return (
    <main className={tw("account-page")}>
      <section className={tw("account-welcome shell")}>
        <p className={tw("eyebrow")}>MY ACCOUNT</p>
        <h1>Welcome back, {auth.user.first_name || "there"}</h1>
        <p>{isStaff ? 'Manage your account details.' : 'Manage quote requests, orders, account details and your saved address.'}</p>
      </section>
      <section className={tw("account-body")}>
        <div className={tw("shell account-grid")}>
          <aside className={tw("account-nav")}>
            <div className={tw(`account-nav-summary ${isStaff ? 'single' : ''}`)}>
              <div className={tw("account-person")}>
                <span>{initials(auth.user)}</span>
                <div>
                  <OverflowTooltipText as="strong" text={name} />
                  <OverflowTooltipText as="small" text={auth.user.email} />
                </div>
              </div>
              {!isStaff && selectedOrganization ? <section className={tw("account-workspace")} aria-label="Current organization"><div className="grid gap-2"><div className="flex min-w-0 items-center justify-between gap-3"><span className="inline-flex items-center gap-2 text-xs font-bold text-muted"><Building2 className="shrink-0 text-brand" size={16} />Organization</span><strong className="truncate text-right text-sm capitalize" title={selectedOrganization.name}>{selectedOrganization.name}</strong></div><div className="flex items-center justify-between gap-3"><span className="text-xs font-bold text-muted">Role</span><strong className="text-right text-sm">{selectedOrganization.role === 'owner' ? 'Owner' : 'License Manager'}</strong></div></div>{workspacesQuery.data && workspacesQuery.data.organizations.length > 1 ? <label className="mt-3 grid gap-1.5 border-t border-border pt-3"><span className="text-xs font-bold text-muted">Switch organization</span><select className="min-h-10 w-full rounded-control border border-border-input bg-white px-3 pr-8 text-sm font-semibold text-ink outline-none focus:border-brand" aria-label="Switch organization" value={organizationId ?? ''} onChange={(event) => { const next = new URLSearchParams(searchParams); next.set('org', event.target.value); next.delete('license'); setSearchParams(next, { replace: true }); }}>{workspacesQuery.data.organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}</select></label> : null}</section> : null}
            </div>
            <button className={tw("account-tab-toggle")} type="button" aria-label={accountMenuOpen ? 'Close account menu' : 'Open account menu'} title="Account menu" aria-expanded={accountMenuOpen} aria-controls="account-section-menu" onClick={() => setAccountMenuOpen((open) => !open)}>
              {accountMenuOpen ? <X size={19} /> : <Menu size={19} />}
            </button>
            <nav className={tw(`account-tab-list ${accountMenuOpen ? 'is-open' : ''}`)} id="account-section-menu" aria-label="Account sections">
              {(isStaff ? STAFF_ACCOUNT_NAV_ITEMS : accountNavItems).map(([value, Icon, label]) => (
                <button
                  className={tw(tab === value ? "active" : "")}
                  type="button"
                  key={value}
                  onClick={() => selectTab(value)}
                >
                  <Icon size={18} />
                  <span>{label}</span>
                </button>
              ))}
              <button
                className={tw("logout-button")}
                type="button"
                onClick={() => { setAccountMenuOpen(false); void auth.logout() }}
              >
                <LogOut size={18} />
                <span>Log out</span>
              </button>
            </nav>
          </aside>
          <div className={tw("account-content")}>
            {!isStaff && organizationSummaryQuery.data?.summary.overflow_quantity ? <section className="mb-5 flex items-start gap-3 rounded-control border border-danger bg-danger-soft p-4 text-sm text-danger" aria-label="License capacity warning">
              <AlertTriangle className="mt-0.5 shrink-0" size={20} />
              <div><strong className="block text-base">License capacity required</strong><p className="mt-1">{organizationSummaryQuery.data.summary.overflow_quantity} licensed radio product(s) are beyond usable license capacity. Add or renew a compatible license to restore full coverage.</p></div>
            </section> : null}
            {!isStaff && pendingInvoiceQuote ? <section className="mb-5 flex flex-wrap items-center justify-between gap-4 rounded-control border border-warning bg-warning-soft p-4 text-sm text-warning" aria-label="Invoice awaiting payment">
              <div className="flex min-w-0 items-start gap-3"><CreditCard className="mt-0.5 shrink-0" size={20} /><div><strong className="block text-base text-ink">Invoice ready for payment</strong><p className="mt-1">Quote {pendingInvoiceQuote.quote_number} created order {pendingInvoiceQuote.order_number}. Review the invoice and complete payment to continue.</p></div></div>
              <button className={tw('action-button action-button-primary action-button-compact')} type="button" onClick={() => selectQuote({ kind: 'quote', value: pendingInvoiceQuote })}>Review invoice</button>
            </section> : null}
            {!isStaff && tab === "overview" ? (
              <AccountOverview
                user={auth.user}
                quotes={quotes}
                orderCount={orderCount}
                quoteCount={quoteCount}
                licenseSummary={organizationSummaryQuery.data?.summary}
                onTab={selectTab}
                onQuoteSelect={(quote) => selectQuote({ kind: 'quote', value: quote })}
              />
            ) : null}
            {!isStaff && tab === 'quotes' ? <>
              <QuotesTable quotes={quotes} loading={quotesQuery.isLoading} onSelect={(quote) => selectQuote({ kind: 'quote', value: quote })} />
              <Pagination page={quotePage} pageSize={QUOTE_PAGE_SIZE} total={quoteCount} loading={quotesQuery.isFetching} className="mt-3" onPageChange={setQuotePage} />
            </> : null}
            {!isStaff && tab === "orders" ? (
              <>
                <OrdersTable orders={orders} loading={ordersQuery.isLoading} paymentsEnabled={paymentStatusQuery.data?.storefront_enabled} organizationId={organizationId} onSelect={(order) => setSelectedRecordState({ kind: 'order', value: order })} />
                <Pagination page={orderPage} pageSize={ORDER_PAGE_SIZE} total={orderCount} loading={ordersQuery.isFetching} className="mt-3" onPageChange={setOrderPage} />
              </>
            ) : null}
            {!isStaff && tab === 'licenses' ? <OrganizationLicensesPanel organizationId={organizationId} workspaceLoading={workspacesQuery.isLoading} workspaceError={workspacesQuery.error} onWorkspaceRetry={() => void workspacesQuery.refetch()} /> : null}
            {!isStaff && tab === 'team' ? <OrganizationTeamPanel organizationId={organizationId} /> : null}
            {!isStaff && tab === 'organization' ? <OrganizationSettingsPanel organizationId={organizationId} canEdit={selectedOrganization?.role === 'owner'} /> : null}
            {tab === "settings" ? <ProfileForm user={auth.user} /> : null}
          </div>
        </div>
      </section>
      {selectedRecord ? <AccountRecordDialog record={selectedRecord} organizationId={organizationId} paymentsEnabled={paymentStatusQuery.data?.storefront_enabled} bankTransferEnabled={paymentStatusQuery.data?.manual_bank_transfer_enabled} onClose={closeRecord} onLinkedQuoteSelect={(quoteNumber) => { setSelectedRecordState(null); const next = new URLSearchParams({ tab: 'quotes', quote: quoteNumber }); if (organizationId) next.set('org', String(organizationId)); setSearchParams(next, { replace: true }); }} /> : null}
    </main>
  );
}
function initials(user: User) {
  const letters =
    `${user.first_name[0] ?? ""}${user.last_name[0] ?? ""}`.trim();
  return letters.toUpperCase() || <UserRound size={22} />;
}
