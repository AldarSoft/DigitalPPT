import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ArrowRight, Check, Clock3, FileText, LockKeyhole, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '../../../contexts/AuthContext'
import { useCart } from '../../../contexts/CartContext'
import { api, ApiError } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { QuoteRequest } from '../../../types'

const quoteSchema = z.object({
  requester_email: z.email('Enter a valid email address'),
  requester_contact_person: z.string().min(2, 'Contact name is required'),
  requester_phone: z.string().min(6, 'Phone number is required'),
  requester_company_name: z.string().optional(),
  notes: z.string().optional(),
})

type QuoteForm = z.infer<typeof quoteSchema>

const quoteDefaults = (user: ReturnType<typeof useAuth>['user']): QuoteForm => ({
  requester_email: user?.email ?? '',
  requester_contact_person: `${user?.first_name ?? ''} ${user?.last_name ?? ''}`.trim(),
  requester_phone: user?.phone_number ?? '',
  requester_company_name: user?.profile.company_name ?? '',
  notes: '',
})

export function CheckoutPage() {
  const cart = useCart()
  const auth = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [completedQuote, setCompletedQuote] = useState<QuoteRequest | null>(null)
  const { register, handleSubmit, reset, setError, formState: { errors, isDirty } } = useForm<QuoteForm>({
    defaultValues: quoteDefaults(auth.user),
  })
  useEffect(() => {
    if (auth.ready && auth.user && !isDirty)
      reset(quoteDefaults(auth.user))
  }, [auth.ready, auth.user, isDirty, reset])
  const quote = useMutation({
    mutationFn: (values: QuoteForm) => api.createQuote({
      ...values,
      items: cart.items.map((item) => ({
        product: item.product.id,
        quantity: item.quantity,
        specifications: {},
      })),
    }),
    onSuccess(value) {
      setCompletedQuote(value)
      cart.clear()
      queryClient.invalidateQueries({ queryKey: ['quotes', 'mine'] })
      toast.success(`Quote request ${value.quote_number} submitted`)
    },
    onError(error) {
      toast.error(error instanceof ApiError ? error.message : 'Could not submit the quote request')
    },
  })

  if (!cart.items.length && !completedQuote) return <Navigate to="/cart" replace />

  if (completedQuote) {
    return (
      <main className={tw('checkout-complete shell')}>
        <span><Check size={36} /></span>
        <p className={tw('eyebrow')}>QUOTE REQUEST RECEIVED</p>
        <h1>Thank you. Our team will review your request.</h1>
        <p>Quote request <strong>{completedQuote.quote_number}</strong> was created with {completedQuote.items.length} {completedQuote.items.length === 1 ? 'item' : 'items'}. A specialist will confirm pricing, availability and delivery.</p>
        <div>
          <Link className={tw('primary-action')} to={auth.user ? '/account' : '/shop'}>{auth.user ? 'View quote requests' : 'Continue shopping'} <ArrowRight size={17} /></Link>
          <button type="button" onClick={() => navigate('/')}>Return home</button>
        </div>
      </main>
    )
  }

  const submit = handleSubmit((values) => {
    const parsed = quoteSchema.safeParse(values)
    if (!parsed.success) {
      parsed.error.issues.forEach((issue) => setError(issue.path[0] as keyof QuoteForm, { message: issue.message }))
      return
    }
    quote.mutate(parsed.data)
  })

  return (
    <main className={tw('checkout-page')}>
      <section className={tw('page-title')}>
        <div className={tw('shell checkout-title')}>
          <div><p className={tw('eyebrow')}>CART&nbsp;&nbsp;/&nbsp;&nbsp;QUOTE REQUEST</p><h1>Request a quote</h1></div>
          <ol><li className={tw('active')}><span>1</span>Contact</li><li><span>2</span>Review</li><li><span>3</span>Submitted</li></ol>
        </div>
      </section>
      <section className={tw('checkout-content')}>
        <form className={tw('shell checkout-grid')} onSubmit={submit}>
          <div className={tw('checkout-fields')}>
            <fieldset>
              <legend>Contact information</legend>
              <label>Contact person<input {...register('requester_contact_person')} /><small>{errors.requester_contact_person?.message}</small></label>
              <div className={tw('field-row')}>
                <label>Email address<input type="email" {...register('requester_email')} /><small>{errors.requester_email?.message}</small></label>
                <label>Phone<input {...register('requester_phone')} /><small>{errors.requester_phone?.message}</small></label>
              </div>
              <label>Company<input {...register('requester_company_name')} /></label>
              <label>Requirements or notes<textarea rows={5} placeholder="Tell us about quantities, delivery timing or configuration requirements." {...register('notes')} /></label>
            </fieldset>
            <div className={tw('payment-excluded')}>
              <Clock3 size={22} />
              <div><strong>Quote request only</strong><p>Your request goes to our team for custom pricing. Direct purchases and payments use the separate cart payment option.</p></div>
            </div>
          </div>
          <aside className={tw('checkout-summary')}>
            <h2>Your quote request</h2>
            {cart.items.map(({ product, quantity, is_automatic }) => (
              <div className={tw('checkout-line')} key={`${product.id}-${is_automatic ? 'automatic' : 'manual'}`}>
                <span>{product.name} x {quantity}{is_automatic ? <small className={tw('automatic-license-label')}><LockKeyhole size={13}/>Automatically added - Required license</small> : null}</span>
                <strong>${(Number(product.current_price) * quantity).toFixed(2)}</strong>
              </div>
            ))}
            <dl>
              <div><dt>Estimated subtotal</dt><dd>${cart.subtotal.toFixed(2)}</dd></div>
              <div><dt>Shipping</dt><dd>To be confirmed</dd></div>
              <div><dt>Final price</dt><dd>Provided by specialist</dd></div>
            </dl>
            <button className={tw('primary-action')} type="submit" disabled={quote.isPending}>
              <FileText size={18} />{quote.isPending ? 'Submitting request...' : 'Submit quote request'}
            </button>
            <p><ShieldCheck size={16} />No payment will be collected</p>
          </aside>
        </form>
      </section>
    </main>
  )
}
