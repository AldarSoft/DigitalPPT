import { lazy, Suspense, useEffect, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { RequireAuth } from './guards/RequireAuth'
import { RequireStaff, RequireStaffPermission } from './guards/RequireStaff'
import { AdminLayout } from '../layouts/AdminLayout'
import { PublicLayout } from '../layouts/PublicLayout'
import { HomePage } from '../pages/HomePage'
import { useAuth } from '../contexts/AuthContext'
import { tw } from '../lib/tailwind-styles'

const AccountPage = lazy(() => import('../features/account/pages/AccountPage').then((module) => ({ default: module.AccountPage })))
const AdminAnalyticsPage = lazy(() => import('../features/admin/pages/AdminAnalyticsPage').then((module) => ({ default: module.AdminAnalyticsPage })))
const AdminCustomersPage = lazy(() => import('../features/admin/pages/AdminCustomersPage').then((module) => ({ default: module.AdminCustomersPage })))
const AdminDashboardPage = lazy(() => import('../features/admin/pages/AdminDashboardPage').then((module) => ({ default: module.AdminDashboardPage })))
const AdminInventoryPage = lazy(() => import('../features/admin/pages/AdminInventoryPage').then((module) => ({ default: module.AdminInventoryPage })))
const AdminOrdersPage = lazy(() => import('../features/admin/pages/AdminOrdersPage').then((module) => ({ default: module.AdminOrdersPage })))
const AdminPaymentsPage = lazy(() => import('../features/admin/pages/AdminPaymentsPage').then((module) => ({ default: module.AdminPaymentsPage })))
const AdminProductsPage = lazy(() => import('../features/admin/pages/AdminProductsPage').then((module) => ({ default: module.AdminProductsPage })))
const AdminQuotesPage = lazy(() => import('../features/admin/pages/AdminQuotesPage').then((module) => ({ default: module.AdminQuotesPage })))
const AdminSiteSettingsPage = lazy(() => import('../features/admin/pages/AdminSiteSettingsPage').then((module) => ({ default: module.AdminSiteSettingsPage })))
const LoginPage = lazy(() => import('../features/auth/pages/LoginPage').then((module) => ({ default: module.LoginPage })))
const RegisterPage = lazy(() => import('../features/auth/pages/RegisterPage').then((module) => ({ default: module.RegisterPage })))
const ResetPasswordPage = lazy(() => import('../features/auth/pages/ResetPasswordPage').then((module) => ({ default: module.ResetPasswordPage })))
const VerifyEmailPage = lazy(() => import('../features/auth/pages/VerifyEmailPage').then((module) => ({ default: module.VerifyEmailPage })))
const ClaimQuotePage = lazy(() => import('../features/auth/pages/ClaimQuotePage').then((module) => ({ default: module.ClaimQuotePage })))
const CartPage = lazy(() => import('../features/cart/pages/CartPage').then((module) => ({ default: module.CartPage })))
const CheckoutPage = lazy(() => import('../features/checkout/pages/CheckoutPage').then((module) => ({ default: module.CheckoutPage })))
const PaymentPage = lazy(() => import('../features/payments/pages/PaymentPage').then((module) => ({ default: module.PaymentPage })))
const ProductDetailsPage = lazy(() => import('../features/products/pages/ProductDetailsPage').then((module) => ({ default: module.ProductDetailsPage })))
const ShopPage = lazy(() => import('../features/products/pages/ShopPage').then((module) => ({ default: module.ShopPage })))
const AdminLicenseDetailPage = lazy(() => import('../features/licensing/pages/AdminLicenseDetailPage').then((module) => ({ default: module.AdminLicenseDetailPage })))
const AdminLicensesPage = lazy(() => import('../features/licensing/pages/AdminLicensesPage').then((module) => ({ default: module.AdminLicensesPage })))
const AcceptOrganizationInvitationPage = lazy(() => import('../features/licensing/pages/AcceptOrganizationInvitationPage').then((module) => ({ default: module.AcceptOrganizationInvitationPage })))
const NotFoundPage = lazy(() => import('../pages/NotFoundPage').then((module) => ({ default: module.NotFoundPage })))

function RouteScrollReset() {
  const location = useLocation()

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
  }, [location.pathname])

  return null
}

export function AppRouter() {
  return (
    <>
      <RouteScrollReset />
      <Suspense fallback={<main className="route-loading">Loading page...</main>}>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<HomePage />} />
          <Route path="shop" element={<ShopPage />} />
          <Route path="products/:slug" element={<ProductDetailsPage />} />
          <Route path="cart" element={<CartPage />} />
          <Route path="checkout" element={<CheckoutPage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route path="auth/reset-password" element={<ResetPasswordPage />} />
          <Route path="auth/verify-email" element={<VerifyEmailPage />} />
          <Route path="auth/claim-quote" element={<ClaimQuotePage />} />
          <Route path="invite" element={<AcceptOrganizationInvitationPage />} />
          <Route element={<RequireAuth />}>
            <Route path="account" element={<AccountPage />} />
            <Route path="payment" element={<PaymentPage />} />
          </Route>
          <Route element={<RequireStaff />}>
            <Route path="payment-preview" element={<PaymentPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route element={<RequireStaff />}>
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<AdminRoleHome dashboard={<AdminDashboardPage />} />} />
            <Route element={<RequireStaffPermission anyOf={['manage_inventory']} />}>
              <Route path="products" element={<AdminProductsPage />} />
              <Route path="inventory" element={<AdminInventoryPage />} />
            </Route>
            <Route element={<RequireStaffPermission anyOf={['manage_orders']} />}>
              <Route path="orders" element={<AdminOrdersPage />} />
            </Route>
            <Route element={<RequireStaffPermission anyOf={['manage_payment_settings', 'confirm_bank_payments']} />}>
              <Route path="payments" element={<AdminPaymentsPage />} />
            </Route>
            <Route element={<RequireStaffPermission anyOf={['manage_quotes', 'confirm_bank_payments']} />}>
              <Route path="quotes" element={<AdminQuotesPage />} />
            </Route>
            <Route element={<RequireStaffPermission anyOf={['manage_users']} />}>
              <Route path="customers" element={<AdminCustomersPage />} />
            </Route>
            <Route element={<RequireStaffPermission anyOf={['manage_licenses']} />}>
              <Route path="licenses" element={<AdminLicensesPage />} />
              <Route path="licenses/:organizationId" element={<AdminLicenseDetailPage />} />
            </Route>
            <Route element={<RequireStaffPermission role="Super Administrator" />}>
              <Route path="analytics" element={<AdminAnalyticsPage />} />
            </Route>
            <Route element={<RequireStaffPermission anyOf={['manage_site_settings']} />}>
              <Route path="site-settings" element={<AdminSiteSettingsPage />} />
            </Route>
          </Route>
        </Route>
      </Routes>
      </Suspense>
    </>
  )
}

function AdminRoleHome({ dashboard }: { dashboard: ReactNode }) {
  const { user } = useAuth()
  if ((user?.staff_roles ?? []).includes('Super Administrator')) return dashboard

  const destinations: Array<[string, string[]]> = [
    ['/admin/quotes', ['manage_quotes', 'confirm_bank_payments']],
    ['/admin/orders', ['manage_orders']],
    ['/admin/payments', ['manage_payment_settings', 'confirm_bank_payments']],
    ['/admin/products', ['manage_inventory']],
    ['/admin/licenses', ['manage_licenses']],
    ['/admin/customers', ['manage_users']],
    ['/admin/site-settings', ['manage_site_settings']],
  ]
  const destination = destinations.find(([, permissions]) =>
    permissions.some((permission) => (user?.staff_permissions ?? []).includes(permission)),
  )
  if (destination) return <Navigate to={destination[0]} replace />
  return <main className={tw('admin-page')}><h1>No workspace assigned</h1><p>Ask a super administrator to assign a staff role to this account.</p></main>
}
