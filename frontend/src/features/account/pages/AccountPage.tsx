import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, LayoutDashboard, LogOut, Package, Settings, UserRound } from 'lucide-react'
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

const ORDER_PAGE_SIZE = 8
const QUOTE_PAGE_SIZE = 10
const ACCOUNT_TABS: AccountTab[] = ['overview', 'quotes', 'orders', 'settings']
const STAFF_ACCOUNT_TABS: AccountTab[] = ['settings']

export function AccountPage() {
  const auth = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab') as AccountTab | null;
  const linkedQuoteNumber = searchParams.get('quote');
  const isStaff = Boolean(auth.user?.is_staff);
  const availableTabs = isStaff ? STAFF_ACCOUNT_TABS : ACCOUNT_TABS;
  const tab: AccountTab = requestedTab && availableTabs.includes(requestedTab) ? requestedTab : isStaff ? 'settings' : 'overview';
  const [orderPage, setOrderPage] = useState(1);
  const [quotePage, setQuotePage] = useState(1);
  const [selectedRecordState, setSelectedRecordState] = useState<AccountRecord | null>(null);
  const ordersQuery = useQuery({
    queryKey: ["orders", "mine", orderPage],
    queryFn: () => api.orders(`ordering=-created_at&page=${orderPage}&page_size=${ORDER_PAGE_SIZE}`),
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
  if (!auth.ready)
    return <main className={tw("route-loading")}>Loading account...</main>;
  if (!auth.user)
    return <Navigate to="/login" state={{ from: "/account" }} replace />;
  const orders = ordersQuery.data ? unwrap(ordersQuery.data) : [];
  const quotes = quotesQuery.data ? unwrap(quotesQuery.data) : [];
  const selectedRecord = selectedRecordState ?? (linkedQuoteQuery.data ? { kind: 'quote' as const, value: linkedQuoteQuery.data } : null);
  const orderCount = ordersQuery.data && !Array.isArray(ordersQuery.data) ? ordersQuery.data.count : orders.length;
  const quoteCount = quotesQuery.data && !Array.isArray(quotesQuery.data) ? quotesQuery.data.count : quotes.length;
  const name =
    `${auth.user.first_name} ${auth.user.last_name}`.trim() || auth.user.email;
  const selectTab = (nextTab: AccountTab) => {
    if (nextTab === 'overview') {
      setOrderPage(1);
      setQuotePage(1);
    }
    setSearchParams(nextTab === 'overview' ? {} : { tab: nextTab }, { replace: true });
  };
  const selectQuote = (quote: AccountRecord & { kind: 'quote' }) => {
    setSelectedRecordState(quote);
    setSearchParams({ tab: 'quotes', quote: quote.value.quote_number }, { replace: true });
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
        <p>{isStaff ? 'Manage your account details.' : 'Manage quote requests, past orders, account details and your saved address.'}</p>
      </section>
      <section className={tw("account-body")}>
        <div className={tw("shell account-grid")}>
          <aside className={tw("account-nav")}>
            <div className={tw("account-person")}>
              <span>{initials(auth.user)}</span>
              <div>
                <OverflowTooltipText as="strong" text={name} />
                <OverflowTooltipText as="small" text={auth.user.email} />
              </div>
            </div>
            {(
              isStaff
                ? [["settings", Settings, "Account settings"]]
                : [
                    ["overview", LayoutDashboard, "Overview"],
                    ["quotes", FileText, "Quote requests"],
                    ["orders", Package, "Past orders"],
                    ["settings", Settings, "Account settings"],
                  ]
            ).map(([value, Icon, label]) => (
              <button
                className={tw(tab === value ? "active" : "")}
                type="button"
                key={value}
                onClick={() => selectTab(value)}
              >
                <Icon size={19} />
                <span>{label}</span>
              </button>
            ))}
            <button
              className={tw("logout-button")}
              type="button"
              onClick={() => auth.logout()}
            >
              <LogOut size={19} />
              <span>Log out</span>
            </button>
          </aside>
          <div className={tw("account-content")}>
            {!isStaff && tab === "overview" ? (
              <AccountOverview
                user={auth.user}
                quotes={quotes}
                orderCount={orderCount}
                quoteCount={quoteCount}
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
                <OrdersTable orders={orders} loading={ordersQuery.isLoading} paymentsEnabled={paymentStatusQuery.data?.storefront_enabled} onSelect={(order) => setSelectedRecordState({ kind: 'order', value: order })} />
                <Pagination page={orderPage} pageSize={ORDER_PAGE_SIZE} total={orderCount} loading={ordersQuery.isFetching} className="mt-3" onPageChange={setOrderPage} />
              </>
            ) : null}
            {tab === "settings" ? <ProfileForm user={auth.user} /> : null}
          </div>
        </div>
      </section>
      {selectedRecord ? <AccountRecordDialog record={selectedRecord} paymentsEnabled={paymentStatusQuery.data?.storefront_enabled} onClose={closeRecord} onLinkedQuoteSelect={(quoteNumber) => { setSelectedRecordState(null); setSearchParams({ tab: 'quotes', quote: quoteNumber }, { replace: true }); }} /> : null}
    </main>
  );
}
function initials(user: User) {
  const letters =
    `${user.first_name[0] ?? ""}${user.last_name[0] ?? ""}`.trim();
  return letters.toUpperCase() || <UserRound size={22} />;
}
