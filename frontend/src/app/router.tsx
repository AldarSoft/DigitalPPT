import { useEffect } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { RequireAuth } from './guards/RequireAuth'
import { RequireStaff } from './guards/RequireStaff'
import { AccountPage } from '../features/account/pages/AccountPage'
import { AdminAnalyticsPage } from '../features/admin/pages/AdminAnalyticsPage'
import { AdminCustomersPage } from '../features/admin/pages/AdminCustomersPage'
import { AdminDashboardPage } from '../features/admin/pages/AdminDashboardPage'
import { AdminInventoryPage } from '../features/admin/pages/AdminInventoryPage'
import { AdminOrdersPage } from '../features/admin/pages/AdminOrdersPage'
import { AdminPaymentsPage } from '../features/admin/pages/AdminPaymentsPage'
import { AdminProductsPage } from '../features/admin/pages/AdminProductsPage'
import { AdminQuotesPage } from '../features/admin/pages/AdminQuotesPage'
import { AdminSiteSettingsPage } from '../features/admin/pages/AdminSiteSettingsPage'
import { LoginPage } from '../features/auth/pages/LoginPage'
import { RegisterPage } from '../features/auth/pages/RegisterPage'
import { CartPage } from '../features/cart/pages/CartPage'
import { CheckoutPage } from '../features/checkout/pages/CheckoutPage'
import { PaymentPage } from '../features/payments/pages/PaymentPage'
import { ProductDetailsPage } from '../features/products/pages/ProductDetailsPage'
import { ShopPage } from '../features/products/pages/ShopPage'
import { AdminLicenseDetailPage } from '../features/licensing/pages/AdminLicenseDetailPage'
import { AdminLicensesPage } from '../features/licensing/pages/AdminLicensesPage'
import { AdminLayout } from '../layouts/AdminLayout'
import { PublicLayout } from '../layouts/PublicLayout'
import { HomePage } from '../pages/HomePage'
import { NotFoundPage } from '../pages/NotFoundPage'

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
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<HomePage />} />
          <Route path="shop" element={<ShopPage />} />
          <Route path="products/:slug" element={<ProductDetailsPage />} />
          <Route path="cart" element={<CartPage />} />
          <Route path="checkout" element={<CheckoutPage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
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
            <Route index element={<AdminDashboardPage />} />
            <Route path="products" element={<AdminProductsPage />} />
            <Route path="orders" element={<AdminOrdersPage />} />
            <Route path="payments" element={<AdminPaymentsPage />} />
            <Route path="quotes" element={<AdminQuotesPage />} />
            <Route path="customers" element={<AdminCustomersPage />} />
            <Route path="licenses" element={<AdminLicensesPage />} />
            <Route path="licenses/:organizationId" element={<AdminLicenseDetailPage />} />
            <Route path="inventory" element={<AdminInventoryPage />} />
            <Route path="analytics" element={<AdminAnalyticsPage />} />
            <Route path="site-settings" element={<AdminSiteSettingsPage />} />
          </Route>
        </Route>
      </Routes>
    </>
  )
}
