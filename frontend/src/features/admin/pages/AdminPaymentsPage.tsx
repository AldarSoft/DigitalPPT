import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleDollarSign, CreditCard, ExternalLink, FlaskConical, Landmark, QrCode, ShieldCheck, WalletCards } from 'lucide-react'
import { toast } from 'sonner'
import { Link } from 'react-router-dom'
import { api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import { paymentStatusKey, paymentStatusLabel } from '../../../lib/status-labels'
import type { PaymentAttempt, PaymentProviderCode } from '../../../types'
import { AdminErrorState } from '../components/AdminErrorState'
import { AdminSelect } from '../components/AdminSelect'
import { Metric } from '../components/Metric'

const providerDetails = {
  stripe: { icon: CreditCard, description: 'Hosted Stripe Checkout Sessions are planned for card payments.' },
  paypal: { icon: WalletCards, description: 'PayPal checkout is prepared for a future API connection.' },
  qpay: { icon: QrCode, description: 'QPay is prepared for a future QR invoice and webhook flow.' },
  bank_transfer: { icon: Landmark, description: 'Bank transfer will use manual instructions and reconciliation.' },
} as const

const providerStateLabel = {
  disabled: 'Disabled',
  development_simulator: 'Development simulator',
  development_unavailable: 'Development simulator unavailable',
  credentials_missing: 'Credentials missing',
  adapter_not_implemented: 'Bank adapter not implemented',
  ready: 'Ready for live processing',
} as const

function money(value: number | string, currency: string) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(Number(value))
}

export function AdminPaymentsPage() {
  const queryClient = useQueryClient()
  const [orderNumber, setOrderNumber] = useState('')
  const [provider, setProvider] = useState<PaymentProviderCode>('stripe')
  const [outcome, setOutcome] = useState<PaymentAttempt['status']>('succeeded')
  const [attemptSearch, setAttemptSearch] = useState('')
  const statusQuery = useQuery({ queryKey: ['payment-status'], queryFn: api.paymentStatus })
  const attemptsQuery = useQuery({
    queryKey: ['payment-attempts'],
    queryFn: () => api.paymentAttempts('ordering=-created_at&page_size=20'),
  })
  const ordersQuery = useQuery({
    queryKey: ['payment-test-orders'],
    queryFn: () => api.orders('ordering=-created_at&page_size=100'),
  })

  const attempts = attemptsQuery.data ? unwrap(attemptsQuery.data) : []
  const orders = ordersQuery.data ? unwrap(ordersQuery.data) : []
  const providers = statusQuery.data?.providers ?? []
  const enabledProviders = providers.filter((item) => item.is_enabled)
  const selectedOrder = orders.find((order) => order.order_number === orderNumber)
  const successful = attempts.filter((attempt) => attempt.status === 'succeeded').length
  const configured = providers.filter((item) => item.api_connected).length
  const ready = providers.filter((item) => item.integration_state === 'ready').length
  const visibleAttempts = attempts.filter((attempt) => {
    const query = attemptSearch.trim().toLowerCase()
    if (!query) return true
    return [
      attempt.reference,
      attempt.order_number,
      attempt.renewal_license_number,
      attempt.provider_name,
      attempt.external_reference,
      attempt.status,
    ].some((value) => value?.toLowerCase().includes(query))
  })

  const toggleProvider = useMutation({
    mutationFn: ({ id, is_customer_available }: { id: number; is_customer_available: boolean }) => api.updatePaymentProvider(id, { is_customer_available }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payment-status'] })
      toast.success('Customer payment availability updated')
    },
    onError: () => toast.error('Could not update the provider'),
  })

  const simulate = useMutation({
    mutationFn: api.simulatePayment,
    onSuccess: (attempt) => {
      queryClient.invalidateQueries({ queryKey: ['payment-attempts'] })
      toast.success(`${attempt.reference} created as test data`)
    },
    onError: () => toast.error('Could not run the test payment'),
  })

  const activeProvider = useMemo(
    () => enabledProviders.some((item) => item.code === provider) ? provider : enabledProviders[0]?.code,
    [enabledProviders, provider],
  )

  if (statusQuery.isError || attemptsQuery.isError || ordersQuery.isError) return <AdminErrorState resource="payment workspace" />

  return (
    <main className={tw('admin-page')}>
      <div className={tw('admin-title-row')}>
        <div><p className={tw('admin-breadcrumb')}>Workspace / Payments</p><h1>Payment workspace</h1><p>Prepare providers and test order payments before customer checkout launches.</p></div>
        <Link className={tw('admin-link-button')} to="/payment-preview">Open client preview <ExternalLink size={16} /></Link>
      </div>

      <div className={tw('payment-alert')}>
        <ShieldCheck size={20} />
        <div><strong>{statusQuery.data?.live_processing_available ? 'Live provider processing is enabled' : 'No live provider is enabled'}</strong><p>{statusQuery.data?.live_processing_available ? 'Provider callbacks, reconciliation, and payment attempts should be monitored here.' : 'The development simulator can be used for testing. Credentials alone do not enable a bank provider.'}</p></div>
      </div>

      <section className={tw('admin-stats')}>
        <Metric label="Providers" value={String(providers.length)} icon={CreditCard} />
        <Metric label="Credentials configured" value={String(configured)} icon={ShieldCheck} />
        <Metric label="Live ready" value={String(ready)} icon={CircleDollarSign} />
        <Metric label="Test attempts" value={String(attempts.length)} icon={FlaskConical} />
        <Metric label="Successful attempts" value={String(successful)} icon={CircleDollarSign} />
      </section>

      <section className={tw('payment-provider-grid')} aria-label="Payment providers">
        {providers.map((item) => {
          const detail = providerDetails[item.code]
          const Icon = detail.icon
          return <article className={tw('payment-provider-card')} key={item.id}>
            <header><span><Icon size={19} /></span><div><h2>{item.display_name}</h2><p>{providerStateLabel[item.integration_state]}</p></div></header>
            <p>{detail.description}</p>
            <footer><span>{item.is_customer_available ? item.code === 'bank_transfer' ? 'MANUAL TRANSFER ENABLED' : item.test_mode ? 'TEST MODE ENABLED' : 'CUSTOMER ENABLED' : 'HIDDEN FROM CUSTOMERS'}</span><button className={tw(`payment-toggle ${item.is_customer_available ? 'active' : ''}`)} type="button" role="switch" aria-checked={item.is_customer_available} aria-label={`${item.is_customer_available ? 'Disable' : 'Enable'} ${item.display_name} for customers`} disabled={toggleProvider.isPending} onClick={() => toggleProvider.mutate({ id: item.id, is_customer_available: !item.is_customer_available })} /></footer>
          </article>
        })}
      </section>

      <section className={tw('payment-workspace')}>
        <form className={tw('admin-panel payment-form')} onSubmit={(event) => {
          event.preventDefault()
          if (!orderNumber || !activeProvider) return
          simulate.mutate({ order_number: orderNumber, provider: activeProvider, outcome })
        }}>
          <h2>Run a test payment</h2>
          <p>The server copies the selected order total. The simulation stores no card number, bank credential, or provider secret.</p>
          <label>Order<AdminSelect value={orderNumber} onChange={(event) => setOrderNumber(event.target.value)}><option value="">Select an order</option>{orders.map((order) => <option key={order.id} value={order.order_number}>{order.order_number} - {money(order.total, 'USD')}</option>)}</AdminSelect></label>
          <label>Provider<AdminSelect value={activeProvider ?? ''} onChange={(event) => setProvider(event.target.value as PaymentProviderCode)}><option value="">Select a provider</option>{enabledProviders.map((item) => <option key={item.id} value={item.code}>{item.display_name}</option>)}</AdminSelect></label>
          <label>Result<AdminSelect value={outcome} onChange={(event) => setOutcome(event.target.value as PaymentAttempt['status'])}><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="pending">Pending</option></AdminSelect></label>
          {selectedOrder ? <p><strong>{selectedOrder.customer_first_name} {selectedOrder.customer_last_name}</strong><br />{money(selectedOrder.total, 'USD')} will be recorded as test data.</p> : null}
          <button type="submit" disabled={!orderNumber || !activeProvider || simulate.isPending}><FlaskConical size={17} />{simulate.isPending ? 'Running test...' : 'Run test payment'}</button>
        </form>

        <div className={tw('admin-panel')}>
          <div className={tw('payment-table-head')}><div><h2>Recent attempts</h2><input aria-label="Search payment attempts" placeholder="Search payment or order" value={attemptSearch} onChange={(event) => setAttemptSearch(event.target.value)} /></div><span>{statusQuery.data?.live_processing_available ? 'MONITOR PROVIDER RESULTS' : 'TEST DATA ONLY'}</span></div>
          <div className={tw('admin-table-wrap')}>
            <table className={tw('admin-table admin-table-compact')}><thead><tr><th>Reference</th><th>Order</th><th>Provider</th><th>Amount</th><th>Status</th><th>Provider reference</th><th>Updated</th></tr></thead><tbody>
              {visibleAttempts.map((attempt) => <tr key={attempt.id}><td><strong>{attempt.reference}</strong></td><td>{attempt.order_number ?? attempt.renewal_license_number ?? 'License renewal'}</td><td>{attempt.provider_name}</td><td>{money(attempt.amount, attempt.currency)}</td><td><span className={tw(`status status-${paymentStatusKey(attempt.status)}`)}>{paymentStatusLabel(attempt.status)}</span></td><td>{attempt.external_reference || 'Awaiting provider'}</td><td>{attempt.paid_at ? new Date(attempt.paid_at).toLocaleString() : new Date(attempt.created_at).toLocaleString()}</td></tr>)}
              {!visibleAttempts.length ? <tr><td colSpan={7}>{attempts.length ? 'No payment attempts match this search.' : 'No payment attempts yet.'}</td></tr> : null}
            </tbody></table>
          </div>
        </div>
      </section>
    </main>
  )
}
