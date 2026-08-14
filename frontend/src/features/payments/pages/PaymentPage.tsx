import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { AlertTriangle, ArrowLeft, Check, CreditCard, ExternalLink, Landmark, LockKeyhole, QrCode, ShieldCheck, WalletCards, X } from 'lucide-react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '../../../contexts/AuthContext'
import { useCart } from '../../../contexts/CartContext'
import { api, ApiError, mediaUrl, unwrap } from '../../../lib/api'
import { unitPriceForQuantity } from '../../../lib/pricing'
import { orderStatusLabel } from '../../../lib/status-labels'
import { tw } from '../../../lib/tailwind-styles'
import type { BillingDetails, Order, PaymentAttempt, PaymentProviderCode, User } from '../../../types'

const billingSchema = z.object({
  email: z.email('Enter a valid email address'),
  first_name: z.string().min(1, 'First name is required'),
  last_name: z.string().min(1, 'Last name is required'),
  phone: z.string().min(6, 'Phone number is required'),
  company: z.string(),
  address: z.string().min(3, 'Address is required'),
  city: z.string().min(2, 'City is required'),
  state: z.string(),
  postal_code: z.string().min(2, 'Postal code is required'),
  country: z.string().min(2, 'Country is required'),
})

type BillingForm = z.infer<typeof billingSchema>

function billingDefaults(user: User | null): BillingForm {
  const profile = user?.profile
  const shipping = profile?.use_different_shipping_address
  return {
    email: user?.email ?? '',
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
    phone: user?.phone_number ?? '',
    company: profile?.company_name ?? '',
    address: shipping ? profile?.shipping_address_line_1 ?? '' : profile?.address_line_1 ?? '',
    city: shipping ? profile?.shipping_city ?? '' : profile?.city ?? '',
    state: shipping ? profile?.shipping_state ?? '' : profile?.state ?? '',
    postal_code: shipping ? profile?.shipping_postal_code ?? '' : profile?.postal_code ?? '',
    country: shipping ? profile?.shipping_country ?? '' : profile?.country ?? '',
  }
}

const providerContent = {
  stripe: { title: 'Credit or debit card', short: 'Stripe Checkout', icon: CreditCard, message: 'Continue to Stripe Checkout to enter card details securely.' },
  paypal: { title: 'PayPal', short: 'PayPal account', icon: WalletCards, message: 'Continue to PayPal to review and authorize the payment.' },
  qpay: { title: 'QPay', short: 'Mobile banking QR', icon: QrCode, message: 'A QPay invoice and QR code will be generated for your banking app.' },
  bank_transfer: { title: 'Bank transfer', short: 'Manual confirmation', icon: Landmark, message: 'Bank instructions and a payment reference will be shown after confirmation.' },
} as const

function money(value: number | string, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(Number(value))
}

function newIdempotencyKey() {
  return window.crypto.randomUUID()
}

export function PaymentPage() {
  const auth = useAuth()
  const cart = useCart()
  const location = useLocation()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const requestedOrder = searchParams.get('order')?.trim() ?? ''
  const returnedSessionId = searchParams.get('session')?.trim() ?? ''
  const staffPreview = location.pathname === '/payment-preview'
  const [provider, setProvider] = useState<PaymentProviderCode>('stripe')
  const [createdOrder, setCreatedOrder] = useState<Order | null>(null)
  const idempotencyKey = useRef(newIdempotencyKey())
  const checkoutKey = useRef(newIdempotencyKey())

  const statusQuery = useQuery({ queryKey: ['storefront-payment-status'], queryFn: api.storefrontPaymentStatus })
  const returnedSessionQuery = useQuery({
    queryKey: ['payment-session', returnedSessionId],
    queryFn: () => api.paymentSession(returnedSessionId),
    enabled: Boolean(returnedSessionId && statusQuery.data?.storefront_enabled),
  })
  const resolvedOrderNumber = requestedOrder || returnedSessionQuery.data?.order_number || ''
  const orderQuery = useQuery({
    queryKey: ['payable-order', resolvedOrderNumber, staffPreview],
    queryFn: () => {
      const query = new URLSearchParams({ ordering: '-created_at', page_size: '1' })
      if (resolvedOrderNumber) query.set('search', resolvedOrderNumber)
      else query.set('status', 'pending')
      return api.orders(query.toString())
    },
    enabled: Boolean(resolvedOrderNumber || staffPreview),
  })
  const existingOrder = orderQuery.data ? unwrap(orderQuery.data)[0] : undefined
  const order = existingOrder ?? createdOrder ?? undefined
  const enabledProviders = statusQuery.data?.providers ?? []
  const activeProvider = enabledProviders.some((item) => item.code === provider) ? provider : enabledProviders[0]?.code ?? provider
  const selectedProvider = providerContent[activeProvider]
  const SelectedProviderIcon = selectedProvider.icon

  const { register, handleSubmit, reset, setError, formState: { errors } } = useForm<BillingForm>({
    defaultValues: billingDefaults(auth.user),
  })

  useEffect(() => {
    if (!order) {
      reset(billingDefaults(auth.user))
      return
    }
    reset({
      email: order.customer_email || auth.user?.email || '', first_name: order.customer_first_name || auth.user?.first_name || '',
      last_name: order.customer_last_name || auth.user?.last_name || '', phone: order.customer_phone || auth.user?.phone_number || '', company: order.company_name || auth.user?.profile.company_name || '',
      address: order.shipping_address || auth.user?.profile.address_line_1 || '', city: order.shipping_city || auth.user?.profile.city || '',
      state: order.shipping_state || auth.user?.profile.state || '', postal_code: order.shipping_postal_code || auth.user?.profile.postal_code || '',
      country: order.shipping_country || auth.user?.profile.country || '',
    })
  }, [auth.user, order, reset])

  const createSession = useMutation({
    mutationFn: async (billing: BillingDetails) => {
      let payableOrder = order
      if (!payableOrder) {
        payableOrder = await api.checkout({
          idempotency_key: checkoutKey.current,
          customer_first_name: billing.first_name,
          customer_last_name: billing.last_name,
          customer_email: billing.email,
          customer_phone: billing.phone,
          company_name: billing.company,
          shipping_address: billing.address,
          shipping_city: billing.city,
          shipping_state: billing.state,
          shipping_postal_code: billing.postal_code,
          shipping_country: billing.country,
          notes: '',
          items: cart.items.map(({ product, quantity }) => ({ product: product.id, quantity })),
        })
        setCreatedOrder(payableOrder)
      }
      return api.createPaymentSession({
        order_number: payableOrder.order_number,
        provider: activeProvider,
        idempotency_key: idempotencyKey.current,
        billing,
      })
    },
    onSuccess: (session) => {
      if (!requestedOrder && !returnedSessionId) cart.clear()
      if (!statusQuery.data?.development_simulator && session.checkout_url) window.location.assign(session.checkout_url)
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : 'Could not start payment'),
  })
  const confirmSession = useMutation({
    mutationFn: ({ sessionId, outcome }: { sessionId: string; outcome: 'succeeded' | 'failed' }) => api.simulatePaymentSession(sessionId, outcome),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders', 'mine'] })
      queryClient.invalidateQueries({ queryKey: ['payable-order'] })
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : 'Could not confirm test payment'),
  })

  const activeSession: PaymentAttempt | undefined = confirmSession.data ?? createSession.data ?? returnedSessionQuery.data
  const resetAttempt = () => {
    idempotencyKey.current = newIdempotencyKey()
    createSession.reset()
    confirmSession.reset()
  }

  if (statusQuery.isLoading || returnedSessionQuery.isLoading || orderQuery.isLoading) return <main className={tw('route-loading')}>Preparing secure payment...</main>
  if (statusQuery.isError || returnedSessionQuery.isError || orderQuery.isError) return <main className={tw('route-message')}><AlertTriangle size={34} /><h1>Payment is unavailable</h1><p>Confirm the backend is running and your account session is active.</p></main>
  if (!statusQuery.data?.storefront_enabled) return <main className={tw('route-message')}><CreditCard size={34} /><h1>Online payment is coming soon</h1><p>Your quote and order history remain available in your account.</p><Link className={tw('primary-action')} to="/account">Return to account</Link></main>

  if (activeSession?.status === 'succeeded') return <main className={tw('client-payment-complete')}><span><Check size={28} /></span><p className={tw('eyebrow')}>{activeSession.is_test ? 'TEST PAYMENT CONFIRMED' : 'PAYMENT CONFIRMED'}</p><h1>Payment received.</h1><p>Payment <strong>{activeSession.reference}</strong> was confirmed for order <strong>{activeSession.order_number}</strong>. The order is now {orderStatusLabel(activeSession.order_status)}.</p><div><Link to="/account?tab=orders">View your orders</Link></div></main>

  if (activeSession && ['failed', 'expired', 'cancelled'].includes(activeSession.status)) return <main className={tw('client-payment-complete client-payment-failed')}><span><X size={28} /></span><p className={tw('eyebrow')}>PAYMENT NOT COMPLETED</p><h1>{activeSession.status === 'expired' ? 'The payment session expired.' : 'The payment was declined.'}</h1><p>{activeSession.failure_message || 'No charge was made. You can return and start a new secure payment session.'}</p><div><button type="button" onClick={resetAttempt}>Try again</button><Link to="/account?tab=orders">View your orders</Link></div></main>

  if (activeSession && statusQuery.data.development_simulator) return <main className={tw('client-payment-simulator')}><span><SelectedProviderIcon size={28} /></span><p className={tw('eyebrow')}>DEVELOPMENT PROVIDER SANDBOX</p><h1>{selectedProvider.title}</h1><p>This represents the external provider handoff. Choose a test response to exercise the verified return path. No real payment credentials or funds are involved.</p><dl><div><dt>Order</dt><dd>{activeSession.order_number}</dd></div><div><dt>Amount</dt><dd>{money(activeSession.amount, activeSession.currency)}</dd></div><div><dt>Session</dt><dd>{activeSession.reference}</dd></div></dl><div><button type="button" disabled={confirmSession.isPending} onClick={() => confirmSession.mutate({ sessionId: activeSession.session_id, outcome: 'failed' })}>Simulate decline</button><button type="button" disabled={confirmSession.isPending} onClick={() => confirmSession.mutate({ sessionId: activeSession.session_id, outcome: 'succeeded' })}>{confirmSession.isPending ? 'Confirming...' : 'Simulate successful payment'}</button></div></main>

  if (!order && !cart.items.length) return <main className={tw('route-message')}><CreditCard size={34} /><h1>No products are ready for payment</h1><p>Add products to your cart, or open a pending invoice from your account.</p><Link className={tw('primary-action')} to="/shop">Browse products</Link></main>
  if (order && order.status !== 'pending') return <main className={tw('route-message')}><ShieldCheck size={34} /><h1>This order is not payable</h1><p>Only pending orders and invoices can start a payment session.</p><Link className={tw('primary-action')} to="/account?tab=orders">View your orders</Link></main>

  const submit = handleSubmit((values) => {
    const parsed = billingSchema.safeParse(values)
    if (!parsed.success) {
      parsed.error.issues.forEach((issue) => setError(issue.path[0] as keyof BillingForm, { message: issue.message }))
      return
    }
    createSession.mutate(parsed.data)
  })

  return <main className={tw('client-payment-page')}>
    <section className={tw('page-title')}><div className={tw('shell client-payment-title')}><div><p className={tw('eyebrow')}>ORDER&nbsp;&nbsp;/&nbsp;&nbsp;PAYMENT</p><h1>Secure payment</h1></div><ol><li><span>1</span>Information</li><li className={tw('active')}><span>2</span>Payment</li><li><span>3</span>Complete</li></ol></div></section>
    <section className={tw('shell section')}>
      {statusQuery.data.development_simulator ? <div className={tw('client-payment-preview-note')}><AlertTriangle size={18} /><div><strong>{staffPreview ? 'Staff preview using development payments' : 'Development payment environment'}</strong><p>No provider credentials or real funds are used. Production keeps this simulator disabled.</p></div></div> : null}
      <form className={tw('client-payment-grid')} onSubmit={submit}>
        <div className={tw('client-payment-fields')}>
          <fieldset className={tw('client-payment-panel')}><legend>Billing information</legend><div className={tw('client-payment-field-grid')}>
            <label className="wide">Email address<input type="email" autoComplete="email" {...register('email')} /><small>{errors.email?.message}</small></label>
            <label>First name<input autoComplete="given-name" {...register('first_name')} /><small>{errors.first_name?.message}</small></label>
            <label>Last name<input autoComplete="family-name" {...register('last_name')} /><small>{errors.last_name?.message}</small></label>
            <label>Phone<input autoComplete="tel" {...register('phone')} /><small>{errors.phone?.message}</small></label>
            <label>Company<input autoComplete="organization" {...register('company')} /><small /></label>
            <label className="wide">Address<input autoComplete="street-address" {...register('address')} /><small>{errors.address?.message}</small></label>
            <label>City<input autoComplete="address-level2" {...register('city')} /><small>{errors.city?.message}</small></label>
            <label>State / province<input autoComplete="address-level1" {...register('state')} /><small /></label>
            <label>Postal code<input autoComplete="postal-code" {...register('postal_code')} /><small>{errors.postal_code?.message}</small></label>
            <label>Country<input autoComplete="country-name" {...register('country')} /><small>{errors.country?.message}</small></label>
          </div></fieldset>
          <section className={tw('client-payment-panel')}><div className={tw('client-payment-provider-head')}><h2>Payment method</h2><span><ShieldCheck size={14} />Secure provider handoff</span></div>
            <div className={tw('client-payment-providers')}>{enabledProviders.map((item) => { const content = providerContent[item.code]; const Icon = content.icon; return <label className={activeProvider === item.code ? 'selected' : ''} key={item.code}><input type="radio" name="payment-provider" value={item.code} checked={activeProvider === item.code} onChange={() => setProvider(item.code)} /><span><Icon size={19} /></span><span><strong>{content.title}</strong><small>{content.short}</small></span></label> })}</div>
            <div className={tw('client-payment-handoff')}><ExternalLink size={18} /><div><strong>{selectedProvider.title}</strong><p>{selectedProvider.message} Digital PTT will not receive or store your payment credentials.</p></div></div>
          </section>
        </div>
        <aside className={tw('client-payment-summary')}>
          <h2>Your order</h2>
          <div className={tw('client-payment-order')}>
            {order ? order.items.map((item) => <div key={item.id}><img src={mediaUrl(item.image_url)} alt="" /><span>{item.product_name}<small>{item.sku || 'Product'} - Qty {item.quantity}</small></span><strong>{money(item.line_total)}</strong></div>) : cart.items.map(({ product, quantity }) => <div key={product.id}><img src={mediaUrl(product.images?.[0]?.image_url)} alt="" /><span>{product.name}<small>{product.sku || 'Product'} - Qty {quantity}</small></span><strong>{money(unitPriceForQuantity(product, quantity) * quantity)}</strong></div>)}
          </div>
          <dl className={tw('client-payment-totals')}><div><dt>Subtotal</dt><dd>{money(order?.subtotal ?? cart.subtotal)}</dd></div><div><dt>Shipping</dt><dd>{order ? money(order.shipping_fee) : money(0)}</dd></div><div><dt>Total</dt><dd>{money(order?.total ?? cart.subtotal)}</dd></div></dl>
          <button className={tw('client-payment-submit')} type="submit" disabled={createSession.isPending || !enabledProviders.length}><LockKeyhole size={16} />{createSession.isPending ? 'Creating order...' : `Place order with ${selectedProvider.title}`}</button>
          <p className={tw('client-payment-security')}><ShieldCheck size={14} />Your order is created at the server-confirmed catalog price, then handed to the selected payment provider.</p>
          <Link className={tw('text-link')} to={order ? '/account?tab=orders' : '/cart'}><ArrowLeft size={15} />{order ? 'Back to your orders' : 'Back to cart'}</Link>
        </aside>
      </form>
    </section>
  </main>
}
