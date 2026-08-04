import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, LayoutDashboard, LogOut, MapPin, Package, Settings, UserRound } from 'lucide-react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { User } from '../../../types'
import { AccountOverview } from '../components/AccountOverview'
import { OrdersTable } from '../components/OrdersTable'
import { ProfileForm } from '../components/ProfileForm'
import { QuotesTable } from '../components/QuotesTable'
import type { AccountTab } from '../types'

export function AccountPage() {
  const auth = useAuth();
  const [tab, setTab] = useState<AccountTab>("overview");
  const ordersQuery = useQuery({
    queryKey: ["orders", "mine"],
    queryFn: () => api.orders(),
    enabled: Boolean(auth.user),
  });
  const quotesQuery = useQuery({
    queryKey: ['quotes', 'mine'],
    queryFn: () => api.quotes('ordering=-created_at&page_size=100'),
    enabled: Boolean(auth.user),
  });
  if (!auth.ready)
    return <main className={tw("route-loading")}>Loading account...</main>;
  if (!auth.user)
    return <Navigate to="/login" state={{ from: "/account" }} replace />;
  const orders = ordersQuery.data ? unwrap(ordersQuery.data) : [];
  const quotes = quotesQuery.data ? unwrap(quotesQuery.data) : [];
  const name =
    `${auth.user.first_name} ${auth.user.last_name}`.trim() || auth.user.email;
  return (
    <main className={tw("account-page")}>
      <section className={tw("account-welcome shell")}>
        <p className={tw("eyebrow")}>MY ACCOUNT</p>
        <h1>Welcome back, {auth.user.first_name || "there"}</h1>
        <p>Manage quote requests, past orders, account details and your saved address.</p>
      </section>
      <section className={tw("account-body")}>
        <div className={tw("shell account-grid")}>
          <aside className={tw("account-nav")}>
            <div className={tw("account-person")}>
              <span>{initials(auth.user)}</span>
              <div>
                <strong>{name}</strong>
                <small>{auth.user.email}</small>
              </div>
            </div>
            {(
              [
                ["overview", LayoutDashboard, "Overview"],
                ["quotes", FileText, "Quote requests"],
                ["orders", Package, "Past orders"],
                ["addresses", MapPin, "Address"],
                ["settings", Settings, "Account settings"],
              ] as const
            ).map(([value, Icon, label]) => (
              <button
                className={tw(tab === value ? "active" : "")}
                type="button"
                key={value}
                onClick={() => setTab(value)}
              >
                <Icon size={19} />
                {label}
              </button>
            ))}
            <button
              className={tw("logout-button")}
              type="button"
              onClick={() => auth.logout()}
            >
              <LogOut size={19} />
              Log out
            </button>
          </aside>
          <div className={tw("account-content")}>
            {tab === "overview" ? (
              <AccountOverview user={auth.user} orders={orders} quotes={quotes} onTab={setTab} />
            ) : null}
            {tab === 'quotes' ? <QuotesTable quotes={quotes} loading={quotesQuery.isLoading} /> : null}
            {tab === "orders" ? (
              <OrdersTable orders={orders} loading={ordersQuery.isLoading} />
            ) : null}
            {tab === "addresses" ? (
              <ProfileForm user={auth.user} addressOnly />
            ) : null}
            {tab === "settings" ? <ProfileForm user={auth.user} /> : null}
          </div>
        </div>
      </section>
    </main>
  );
}
function initials(user: User) {
  const letters =
    `${user.first_name[0] ?? ""}${user.last_name[0] ?? ""}`.trim();
  return letters.toUpperCase() || <UserRound size={22} />;
}

