import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, ChevronDown, FileText, LoaderCircle, Minus, Plus, Radio, ShieldCheck } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api, ApiError } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { QuoteRequest } from '../../../types'

export function CoverageQuotePage() {
  const { slug = '' } = useParams()
  const queryClient = useQueryClient()
  const [organizationId, setOrganizationId] = useState<number | null>(null)
  const [selection, setSelection] = useState<Record<number, number>>({})
  const [notes, setNotes] = useState('')
  const [completedQuote, setCompletedQuote] = useState<QuoteRequest | null>(null)

  const productQuery = useQuery({
    queryKey: ['product', slug],
    queryFn: () => api.product(slug),
  })
  const organizationsQuery = useQuery({
    queryKey: ['organization-workspaces'],
    queryFn: api.organizationWorkspaces,
  })
  const organizations = organizationsQuery.data?.organizations ?? []
  const selectedOrganizationId = organizationId
    ?? organizationsQuery.data?.default_organization_id
    ?? organizations[0]?.id
    ?? null

  const product = productQuery.data
  const eligiblePlan = Boolean(
    product
    && product.licensing_role === 'license_product'
    && product.license_billing_model === 'per_radio',
  )
  const optionsQuery = useQuery({
    queryKey: ['coverage-quote-options', selectedOrganizationId, product?.id],
    queryFn: () => api.coverageQuoteOptions(selectedOrganizationId!, product!.id),
    enabled: Boolean(eligiblePlan && selectedOrganizationId && product),
  })

  const selectedTargets = useMemo(() => (optionsQuery.data?.candidates ?? [])
    .map((candidate) => ({
      order_item_id: candidate.order_item_id,
      quantity: Math.min(
        selection[candidate.order_item_id] ?? candidate.available_quantity,
        candidate.available_quantity,
      ),
    }))
    .filter((target) => target.quantity > 0), [optionsQuery.data?.candidates, selection])
  const selectedQuantity = selectedTargets.reduce((total, target) => total + target.quantity, 0)
  const estimatedTotal = selectedQuantity * Number(product?.current_price ?? 0)

  const createQuote = useMutation({
    mutationFn: () => api.createCoverageQuote({
      organization_id: selectedOrganizationId!,
      license_product_id: product!.id,
      targets: selectedTargets,
      notes,
    }),
    onSuccess(quote) {
      setCompletedQuote(quote)
      queryClient.invalidateQueries({ queryKey: ['quotes'] })
      queryClient.invalidateQueries({ queryKey: ['coverage-quote-options'] })
      toast.success(`Coverage quote ${quote.quote_number} submitted`)
    },
    onError(error) {
      toast.error(error instanceof ApiError ? error.message : 'Could not submit the coverage quote')
    },
  })

  if (productQuery.isLoading || organizationsQuery.isLoading) {
    return <main className={tw('route-loading')}><LoaderCircle className="animate-spin" size={28} />Loading coverage options...</main>
  }
  if (!product || productQuery.isError || !eligiblePlan) {
    return <main className={tw('route-message shell')}><FileText size={34} /><h1>Coverage plan unavailable</h1><p>This product cannot be used for a standalone radio coverage request.</p><Link className={tw('primary-action')} to="/shop">Return to shop</Link></main>
  }
  if (completedQuote) {
    return <main className={tw('checkout-complete shell')}>
      <span><Check size={36} /></span>
      <p className={tw('eyebrow')}>COVERAGE QUOTE RECEIVED</p>
      <h1>Your annual radio coverage request is ready for review.</h1>
      <p>Quote <strong>{completedQuote.quote_number}</strong> requests coverage for {selectedQuantity} radio{selectedQuantity === 1 ? '' : 's'}. Coverage will activate only after the quoted payment is confirmed.</p>
      <div><Link className={tw('primary-action')} to="/account?tab=quotes">View quote request <ArrowRight size={17} /></Link><Link to="/shop">Continue shopping</Link></div>
    </main>
  }

  return <main className="bg-canvas pb-16 text-ink">
    <section className="border-b border-border bg-white">
      <div className={`${tw('shell')} py-8 max-[640px]:py-6`}>
        <p className={tw('eyebrow')}>ANNUAL RADIO COVERAGE</p>
        <h1 className="max-w-3xl text-[32px] font-semibold leading-tight max-[640px]:text-[26px]">Request radio coverage</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">Annual coverage for radios you already own. Coverage starts after payment confirmation.</p>
      </div>
    </section>

    <section className={`${tw('shell')} grid items-start gap-8 py-8 [grid-template-columns:minmax(0,1fr)_340px] max-[900px]:grid-cols-1 max-[640px]:gap-6 max-[640px]:py-6`}>
      <div className="min-w-0">
        <label className="grid max-w-xl gap-2 text-sm font-bold">
          Organization
          <span className="relative block">
            <select className="min-h-11 w-full min-w-0 appearance-none rounded-control border border-border-input bg-white py-2 pl-3 pr-11 font-normal" value={selectedOrganizationId ?? ''} onChange={(event) => setOrganizationId(Number(event.target.value))}>
              {organizations.map((organization) => <option value={organization.id} key={organization.id}>{organization.name}</option>)}
            </select>
            <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-muted" size={17} strokeWidth={2} />
          </span>
        </label>

        {!organizations.length ? <div className="mt-5 rounded-panel border border-warning bg-warning-soft p-5"><strong>No organization is available</strong><p className="mt-2 text-sm text-muted">Create an organization before requesting radio coverage.</p><Link className={`${tw('action-button action-button-secondary')} mt-4`} to="/account?tab=organization-settings">Open organization settings</Link></div> : null}
        {optionsQuery.isLoading ? <div className="mt-5 flex min-h-52 items-center justify-center rounded-panel border border-border bg-white text-sm text-muted"><LoaderCircle className="mr-2 animate-spin" size={20} />Checking radio coverage...</div> : null}
        {optionsQuery.isError ? <div className="mt-5 rounded-panel border border-danger bg-danger-soft p-5 text-sm text-danger">We could not verify current radio coverage. Please refresh and try again.</div> : null}
        {optionsQuery.data && !optionsQuery.data.candidates.length ? <div className="mt-6 flex min-h-60 flex-col items-center justify-center border-y border-border px-5 py-8 text-center"><ShieldCheck className="text-success" size={32} /><h2 className="mt-4 text-lg font-semibold">No radios available for coverage</h2><p className="mt-2 max-w-md text-sm leading-relaxed text-muted">There are no uncovered radios available for this plan. Radios included in pending quotes are excluded.</p><Link className="mt-5 inline-flex min-h-10 items-center gap-2 text-sm font-semibold text-brand hover:underline" to="/account?tab=licenses">View your licenses <ArrowRight size={16} /></Link></div> : null}

        {optionsQuery.data?.candidates.length ? <section className="mt-5 overflow-hidden rounded-panel border border-border bg-white">
          <header className="border-b border-border px-5 py-4"><h2 className="text-xl">Uncovered radios</h2><p className="mt-1 text-sm text-muted">Choose the quantities this quote should cover.</p></header>
          <div className="divide-y divide-border-soft">
            {optionsQuery.data.candidates.map((candidate) => {
              const quantity = Math.min(
                selection[candidate.order_item_id] ?? candidate.available_quantity,
                candidate.available_quantity,
              )
              const checked = quantity > 0
              return <div className="grid items-center gap-4 px-5 py-4 [grid-template-columns:auto_minmax(0,1fr)_auto] max-[600px]:grid-cols-[auto_minmax(0,1fr)]" key={candidate.order_item_id}>
                <input className="size-4 accent-brand" type="checkbox" checked={checked} aria-label={`Select ${candidate.product_name}`} onChange={(event) => setSelection((current) => ({ ...current, [candidate.order_item_id]: event.target.checked ? candidate.available_quantity : 0 }))} />
                <div className="min-w-0"><strong className="block text-sm">{candidate.product_name}</strong><span className="mt-1 block text-xs text-muted">{candidate.product_sku} · {candidate.order_number} · {new Date(candidate.ordered_at).toLocaleDateString()}</span><span className="mt-1 block text-xs font-semibold text-danger">{candidate.available_quantity} radio{candidate.available_quantity === 1 ? '' : 's'} need coverage</span></div>
                <div className={`grid grid-cols-[36px_48px_36px] items-center overflow-hidden rounded-control border border-border-input max-[600px]:col-start-2 max-[600px]:w-max ${checked ? '' : 'opacity-45'}`}>
                  <button className="inline-flex size-9 items-center justify-center border-0 bg-white" type="button" disabled={!checked || quantity <= 1} onClick={() => setSelection((current) => ({ ...current, [candidate.order_item_id]: Math.max(1, quantity - 1) }))}><Minus size={15} /></button>
                  <strong className="text-center text-sm">{quantity}</strong>
                  <button className="inline-flex size-9 items-center justify-center border-0 bg-white" type="button" disabled={!checked || quantity >= candidate.available_quantity} onClick={() => setSelection((current) => ({ ...current, [candidate.order_item_id]: Math.min(candidate.available_quantity, quantity + 1) }))}><Plus size={15} /></button>
                </div>
              </div>
            })}
          </div>
        </section> : null}

        {optionsQuery.data?.candidates.length ? <label className="mt-5 grid gap-2 text-sm font-bold">Notes for our team<textarea className="min-h-28 resize-y rounded-control border border-border-input bg-white p-3 font-normal" value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} placeholder="Optional deployment, billing or timing details" /></label> : null}
      </div>

      <aside aria-label="Coverage quote summary" className="sticky top-24 min-w-0 rounded-panel border border-border bg-white p-5 max-[900px]:static">
        <div className="flex items-start gap-3"><span className="inline-flex size-10 shrink-0 items-center justify-center rounded-control bg-brand-soft text-brand"><Radio size={21} /></span><div className="min-w-0 break-words"><strong className="block">{product.name}</strong><span className="mt-1 block text-xs text-muted">{product.license_term_days ?? 365}-day coverage</span></div></div>
        <dl className="mt-5 grid gap-3 border-y border-border-soft py-4 text-sm"><div className="flex justify-between gap-4"><dt className="text-muted">Selected radios</dt><dd className="font-bold">{selectedQuantity}</dd></div><div className="flex justify-between gap-4"><dt className="text-muted">Price per radio</dt><dd className="font-mono font-bold">${Number(product.current_price).toFixed(2)}</dd></div><div className="flex justify-between gap-4"><dt className="font-bold">Estimated subtotal</dt><dd className="font-mono font-bold text-brand">${estimatedTotal.toFixed(2)}</dd></div></dl>
        <p className="mt-4 text-xs leading-relaxed text-muted">The final invoice is reviewed by our team. No payment is collected when this request is submitted.</p>
        <button className={`${tw('action-button action-button-primary')} mt-5 w-full whitespace-normal text-center disabled:cursor-not-allowed`} type="button" disabled={!selectedQuantity || createQuote.isPending} onClick={() => createQuote.mutate()}><FileText className="shrink-0" size={18} />{createQuote.isPending ? 'Submitting...' : 'Request coverage quote'}</button>
      </aside>
    </section>
  </main>
}
