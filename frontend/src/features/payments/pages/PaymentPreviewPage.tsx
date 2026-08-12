import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { AlertTriangle, ArrowLeft, Check, CreditCard, ExternalLink, Landmark, LockKeyhole, QrCode, ShieldCheck, WalletCards } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { api, mediaUrl, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { PaymentProviderCode } from '../../../types'

const billingSchema = z.object({
  email: z.email('Enter a valid email address'),
  first_name: z.string().min(1, 'First name is required'),
  last_name: z.string().min(1, 'Last name is required'),
  company: z.string(),
  address: z.string().min(3, 'Address is required'),
  city: z.string().min(2, 'City is required'),
  state: z.string(),
  postal_code: z.string().min(2, 'Postal code is required'),
  country: z.string().min(2, 'Country is required'),
})

type BillingForm = z.infer<typeof billingSchema>
type PreviewState = 'form' | 'redirecting' | 'complete'

const providerContent = {
  stripe: {
    title: 'Credit or debit card',
    short: 'Stripe Checkout',
    icon: CreditCard,
    message: 'You will continue to Stripe Checkout to enter card details securely.',
  },
  paypal: {
    title: 'PayPal',
    short: 'PayPal account',
    icon: WalletCards,
    message: 'You will continue to PayPal to review and authorize the payment.',
  },
  qpay: {
    title: 'QPay',
    short: 'Mobile banking QR',
    icon: QrCode,
    message: 'A QPay invoice and QR code will be generated for your banking app.',
  },
  bank_transfer: {
    title: 'Bank transfer',
    short: 'Manual confirmation',
    icon: Landmark,
    message: 'Bank instructions and a payment reference will be shown after confirmation.',
  },
} as const

function money(value: number | string, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(Number(value))
}

export function PaymentPreviewPage() {
  const auth = useAuth()
  const [searchParams] = useSearchParams()
  const requestedOrder = searchParams.get('order')?.trim() ?? ''
  const [provider, setProvider] = useState<PaymentProviderCode>('stripe')
  const [previewState, setPreviewState] = useState<PreviewState>('form')

  const orderQuery = useQuery({
    queryKey: ['payment-preview-order', requestedOrder],
    queryFn: () => {
      const query = new URLSearchParams({ ordering: '-created_at', page_size: '1' })
      if (requestedOrder) query.set('search', requestedOrder)
      return api.orders(query.toString())
    },
  })
  const providerQuery = useQuery({ queryKey: ['payment-status'], queryFn: api.paymentStatus })
  const order = orderQuery.data ? unwrap(orderQuery.data)[0] : undefined
  const enabledProviders = providerQuery.data?.providers.filter((item) => item.is_enabled) ?? []
  const activeProvider = enabledProviders.some((item) => item.code === provider)
    ? provider
    : enabledProviders[0]?.code ?? provider
  const selectedProvider = providerContent[activeProvider]

  const { register, handleSubmit, reset, setError, formState: { errors } } = useForm<BillingForm>({
    defaultValues: {
      email: auth.user?.email ?? '',
      first_name: auth.user?.first_name ?? '',
      last_name: auth.user?.last_name ?? '',
      company: auth.user?.profile.company_name ?? '',
      address: auth.user?.profile.address_line_1 ?? '',
      city: auth.user?.profile.city ?? '',
      state: auth.user?.profile.state ?? '',
      postal_code: auth.user?.profile.postal_code ?? '',
      country: auth.user?.profile.country ?? '',
    },
  })

  useEffect(() => {
    if (!order) return
    reset({
      email: order.customer_email || auth.user?.email || '',
      first_name: order.customer_first_name || auth.user?.first_name || '',
      last_name: order.customer_last_name || auth.user?.last_name || '',
      company: order.company_name || auth.user?.profile.company_name || '',
      address: order.shipping_address || auth.user?.profile.address_line_1 || '',
      city: order.shipping_city || auth.user?.profile.city || '',
      state: order.shipping_state || auth.user?.profile.state || '',
      postal_code: order.shipping_postal_code || auth.user?.profile.postal_code || '',
      country: order.shipping_country || auth.user?.profile.country || '',
    })
  }, [auth.user, order, reset])

  useEffect(() => {
    if (previewState !== 'redirecting') return
    const timer = window.setTimeout(() => setPreviewState('complete'), 900)
    return () => window.clearTimeout(timer)
  }, [previewState])

  if (orderQuery.isLoading || providerQuery.isLoading) return <main className={tw('route-loading')}>Preparing payment preview...</main>
  if (orderQuery.isError || providerQuery.isError) return <main className={tw('route-message')}><AlertTriangle size={34} /><h1>Payment preview unavailable</h1><p>Confirm the backend is running and your staff session is active.</p></main>
  if (!order) return <main className={tw('route-message')}><CreditCard size={34} /><h1>No order available for preview</h1><p>Create or approve an order first, then return to this hidden payment preview.</p><Link className={tw('primary-action')} to="/admin/orders">View orders</Link></main>

  if (previewState === 'complete') return <main className={tw('client-payment-complete')}><span><Check size={28} /></span><p className={tw('eyebrow')}>PREVIEW COMPLETE</p><h1>The provider handoff is ready for integration.</h1><p>No payment was created and order <strong>{order.order_number}</strong> was not changed. When live APIs are connected, this state will be replaced by a verified provider return and webhook result.</p><div><button type="button" onClick={() => setPreviewState('form')}>Back to preview</button><Link to="/admin/payments">Payment workspace</Link></div></main>

  const submit = handleSubmit((values) => {
    const parsed = billingSchema.safeParse(values)
    if (!parsed.success) {
      parsed.error.issues.forEach((issue) => setError(issue.path[0] as keyof BillingForm, { message: issue.message }))
      return
    }
    setPreviewState('redirecting')
  })

  return <main className={tw('client-payment-page')}>
    <section className={tw('page-title')}><div className={tw('shell client-payment-title')}><div><p className={tw('eyebrow')}>ORDER&nbsp;&nbsp;/&nbsp;&nbsp;PAYMENT PREVIEW</p><h1>Secure payment</h1></div><ol><li><span>1</span>Information</li><li className={tw('active')}><span>2</span>Payment</li><li><span>3</span>Complete</li></ol></div></section>
    <section className={tw('shell section')}>
      <div className={tw('client-payment-preview-note')}><AlertTriangle size={18} /><div><strong>Staff preview only</strong><p>This route is hidden from customers. It does not contact a payment provider, collect card details, or change the order.</p></div></div>
      <form className={tw('client-payment-grid')} onSubmit={submit}>
        <div className={tw('client-payment-fields')}>
          <fieldset className={tw('client-payment-panel')}><legend>Billing information</legend><div className={tw('client-payment-field-grid')}>
            <label className="wide">Email address<input type="email" autoComplete="email" {...register('email')} /><small>{errors.email?.message}</small></label>
            <label>First name<input autoComplete="given-name" {...register('first_name')} /><small>{errors.first_name?.message}</small></label>
            <label>Last name<input autoComplete="family-name" {...register('last_name')} /><small>{errors.last_name?.message}</small></label>
            <label className="wide">Company<input autoComplete="organization" {...register('company')} /><small /></label>
            <label className="wide">Address<input autoComplete="street-address" {...register('address')} /><small>{errors.address?.message}</small></label>
            <label>City<input autoComplete="address-level2" {...register('city')} /><small>{errors.city?.message}</small></label>
            <label>State / province<input autoComplete="address-level1" {...register('state')} /><small /></label>
            <label>Postal code<input autoComplete="postal-code" {...register('postal_code')} /><small>{errors.postal_code?.message}</small></label>
            <label>Country<input autoComplete="country-name" {...register('country')} /><small>{errors.country?.message}</small></label>
          </div></fieldset>
          <section className={tw('client-payment-panel')}><div className={tw('client-payment-provider-head')}><h2>Payment method</h2><span><ShieldCheck size={14} />Secure provider handoff</span></div>
            <div className={tw('client-payment-providers')}>
              {providerQuery.data?.providers.map((item) => {
                const content = providerContent[item.code]
                const Icon = content.icon
                return <label className={`${activeProvider === item.code ? 'selected' : ''} ${item.is_enabled ? '' : 'disabled'}`} key={item.id}><input type="radio" name="payment-provider" value={item.code} checked={activeProvider === item.code} disabled={!item.is_enabled} onChange={() => setProvider(item.code)} /><span><Icon size={19} /></span><span><strong>{content.title}</strong><small>{item.is_enabled ? content.short : 'Unavailable'}</small></span></label>
              })}
            </div>
            <div className={tw('client-payment-handoff')}><ExternalLink size={18} /><div><strong>{selectedProvider.title}</strong><p>{selectedProvider.message} Digital PTT will not receive or store your payment credentials.</p></div></div>
          </section>
        </div>
        <aside className={tw('client-payment-summary')}><h2>Your order</h2><div className={tw('client-payment-order')}>{order.items.map((item) => <div key={item.id}><img src={mediaUrl(item.image_url)} alt="" /><span>{item.product_name}<small>{item.sku || 'Product'} · Qty {item.quantity}</small></span><strong>{money(item.line_total)}</strong></div>)}</div><dl className={tw('client-payment-totals')}><div><dt>Subtotal</dt><dd>{money(order.subtotal)}</dd></div><div><dt>Shipping</dt><dd>Included</dd></div><div><dt>Total</dt><dd>{money(order.total)}</dd></div></dl><button className={tw('client-payment-submit')} type="submit" disabled={previewState === 'redirecting' || !enabledProviders.length}><LockKeyhole size={16} />{previewState === 'redirecting' ? 'Preparing secure handoff...' : `Preview ${selectedProvider.title}`}</button><p className={tw('client-payment-security')}><ShieldCheck size={14} />Test UI only. No payment will be collected.</p><Link className={tw('text-link')} to="/admin/payments"><ArrowLeft size={15} />Back to payment workspace</Link></aside>
      </form>
    </section>
  </main>
}
