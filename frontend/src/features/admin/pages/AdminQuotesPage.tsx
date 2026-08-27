import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, BadgeCheck, Clock3, CreditCard, Download, FileText, MessageSquare, Search, Send, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api, ApiError, mediaUrl, unwrap } from '../../../lib/api'
import { StatusTimeline } from '../../../components/StatusTimeline'
import { ProductThumbnail } from '../../../components/ProductThumbnail'
import { Pagination } from '../../../components/Pagination'
import { tw } from '../../../lib/tailwind-styles'
import { quoteStatusKey, quoteStatusLabel } from '../../../lib/status-labels'
import type { QuoteRequest } from '../../../types'
import { AdminErrorState } from '../components/AdminErrorState'
import { AdminSelect } from '../components/AdminSelect'
import { Metric } from '../components/Metric'
import { exportAdminReport } from '../utils/exportAdminReport'

const PAGE_SIZE = 10

const QUOTE_STEPS = [
  { value: 'new', label: 'Pending' },
  { value: 'reviewing', label: 'Processing' },
  { value: 'quoted', label: 'Invoice ready' },
  { value: 'approved', label: 'Completed' },
] as const

export function AdminQuotesPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState(() => searchParams.get('status') ?? '')
  const [page, setPage] = useState(1)
  const [selectedQuote, setSelectedQuote] = useState<QuoteRequest | null>(null)
  const [confirmingClose, setConfirmingClose] = useState(false)
  const [itemPrices, setItemPrices] = useState<Record<number, string>>({})
  const [quotedShipping, setQuotedShipping] = useState<string | null>(null)
  const [adminMessage, setAdminMessage] = useState<string | null>(null)
  const [requestAdditionalInformation, setRequestAdditionalInformation] = useState(false)
  const [message, setMessage] = useState('')
  const messagesRef = useRef<HTMLDivElement>(null)
  const messageInputRef = useRef<HTMLTextAreaElement>(null)
  const summaryQuery = useQuery({
    queryKey: ['admin-quotes', 'summary'],
    queryFn: () => api.quotes('ordering=-created_at&page_size=100'),
  })
  const quotesQuery = useQuery({
    queryKey: ['admin-quotes', 'list', search, status, page],
    queryFn: () => {
      const query = new URLSearchParams()
      if (search) query.set('search', search)
      if (status) query.set('display_status', status)
      query.set('ordering', '-created_at')
      query.set('page', String(page))
      query.set('page_size', String(PAGE_SIZE))
      return api.quotes(query.toString())
    },
    placeholderData: keepPreviousData,
  })
  const linkedQuoteNumber = searchParams.get('quote')
  const activeQuoteNumber = selectedQuote?.quote_number ?? linkedQuoteNumber
  const linkedQuoteQuery = useQuery({
    queryKey: ['admin-quotes', 'detail', activeQuoteNumber],
    queryFn: () => api.quote(activeQuoteNumber!),
    enabled: Boolean(activeQuoteNumber),
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  })
  const allQuotes = summaryQuery.data ? unwrap(summaryQuery.data) : []
  const quotes = quotesQuery.data ? unwrap(quotesQuery.data) : []
  const quoteTotal = quotesQuery.data && !Array.isArray(quotesQuery.data) ? quotesQuery.data.count : quotes.length
  const selected = linkedQuoteQuery.data ?? selectedQuote ?? null
  useEffect(() => {
    const requestedStatus = searchParams.get('status') ?? ''
    if (requestedStatus === status) return
    setStatus(requestedStatus)
    setPage(1)
  }, [searchParams, status])
  useEffect(() => {
    const messageList = messagesRef.current
    if (messageList) messageList.scrollTop = messageList.scrollHeight
  }, [selected?.messages])
  useEffect(() => {
    const input = messageInputRef.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(Math.max(input.scrollHeight, 80), 240)}px`
  }, [message])
  const applyQuote = (value: QuoteRequest, notice: string) => {
    queryClient.setQueryData(['admin-quotes', 'detail', value.quote_number], value)
    setSelectedQuote(value)
    setItemPrices(Object.fromEntries(value.items.map((item) => [item.id, item.quoted_unit_price ?? item.suggested_unit_price ?? ''])))
    setQuotedShipping(value.quoted_shipping || '0.00')
    setAdminMessage(value.admin_message || '')
    setRequestAdditionalInformation(false)
    setMessage('')
    setConfirmingClose(false)
    queryClient.invalidateQueries({ queryKey: ['admin-quotes'] })
    queryClient.invalidateQueries({ queryKey: ['admin-orders'] })
    toast.success(notice)
  }
  const mutationError = (error: Error) => toast.error(error instanceof ApiError ? error.message : 'Could not update the quote')
  const update = useMutation({
    mutationFn: ({ quoteNumber, data }: { quoteNumber: string; data: Parameters<typeof api.updateQuote>[1] }) => api.updateQuote(quoteNumber, data),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status >= 400 && error.status < 500)
      && failureCount < 3,
    retryDelay: (attemptIndex) => 500 * (attemptIndex + 1),
    onSuccess: (value) => applyQuote(value, value.status === 'cancelled' ? 'Quote cancelled' : 'Quote request updated'),
    onError: mutationError,
  })
  const invoice = useMutation({
    mutationFn: () => api.issueQuoteInvoice(selected!.quote_number, {
      items: selected!.items.map((item) => ({ id: item.id, quoted_unit_price: itemPrices[item.id] ?? item.quoted_unit_price ?? item.suggested_unit_price ?? '' })),
      quoted_shipping: quotedShipping ?? selected!.quoted_shipping ?? '0.00',
      admin_message: adminMessage ?? selected!.admin_message ?? '',
    }),
    onSuccess: (value) => applyQuote(value, selected?.invoice_number ? 'Invoice updated and resent.' : 'PDF invoice created and sent to the customer.'),
    onError: mutationError,
  })
  const sendMessage = useMutation({
    mutationFn: () => api.addQuoteMessage(selected!.quote_number, message),
    onSuccess: (value) => applyQuote(value, 'Message sent.'),
    onError: mutationError,
  })
  if (quotesQuery.isError || summaryQuery.isError) return <AdminErrorState resource="quote requests" />

  const openQuote = (quote: QuoteRequest) => {
    setConfirmingClose(false)
    setItemPrices(Object.fromEntries(quote.items.map((item) => [item.id, item.quoted_unit_price ?? item.suggested_unit_price ?? ''])))
    setQuotedShipping(quote.quoted_shipping || '0.00')
    setAdminMessage(quote.admin_message || '')
    setRequestAdditionalInformation(false)
    setMessage('')
    setSelectedQuote(quote)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('quote', quote.quote_number)
      return next
    }, { replace: true })
  }

  const closeQuote = () => {
    setSelectedQuote(null)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('quote')
      return next
    }, { replace: true })
  }

  const changeStatusFilter = (value: string) => {
    setStatus(value)
    setPage(1)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set('status', value)
      else next.delete('status')
      return next
    }, { replace: true })
  }

  const sendInvoice = () => {
    if (!selected) return
    if (selected.items.some((item) => Number(itemPrices[item.id] ?? item.quoted_unit_price ?? item.suggested_unit_price ?? 0) <= 0)) {
      toast.error('Add a valid unit price for every item')
      return
    }
    invoice.mutate()
  }

  const invoiceSent = Boolean(selected?.invoiced_at && selected.quoted_total)
  const canEditInvoice = selected?.status === 'reviewing' || (selected?.status === 'quoted' && selected.order_status === 'pending')
  const canSendInvoice = Boolean(canEditInvoice)

  return (
    <main className={tw('admin-page')}>
      <div className={tw('admin-title-row')}>
        <div><p className={tw('admin-breadcrumb')}>Workspace / Quotes</p><h1>Quote requests</h1><p>Negotiate requirements, agree pricing and issue customer invoices.</p></div>
        <button type="button" onClick={() => void exportAdminReport({ kind: 'quotes', rows: quotes })}><Download size={18} />Export</button>
      </div>
      <section className={tw('admin-stats order-stats')}>
        <Metric label="Total requests" value={String(allQuotes.length)} icon={FileText} />
        <Metric label="Needs review" value={String(allQuotes.filter((quote) => quote.status === 'new' || quote.status === 'reviewing').length)} icon={Clock3} />
        <Metric label="Awaiting payment" value={String(allQuotes.filter((quote) => quote.status === 'quoted' && quote.order_status === 'pending').length)} icon={CreditCard} />
        <Metric label="Completed" value={String(allQuotes.filter((quote) => quoteStatusKey(quote.status) === 'completed').length)} icon={BadgeCheck} />
      </section>
      <section className={tw('admin-panel admin-section-gap')}>
        <div className={tw('orders-toolbar')}>
          <h2>Recent requests</h2>
          <div><Search size={18} /><input placeholder="Search quote or customer" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} /></div>
          <AdminSelect aria-label="Filter by quote status" value={status} onChange={(event) => changeStatusFilter(event.target.value)}>
            <option value="">All status</option><option value="pending">Pending review</option><option value="processing">In progress</option><option value="completed">Completed</option>
          </AdminSelect>
        </div>
        <div className={tw('admin-table-wrap')}>
          <table className={tw('admin-table')}>
            <thead><tr><th>Quote ID</th><th>Requester</th><th>Date</th><th>Items</th><th>Linked order</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>{quotes.length ? quotes.map((quote) => (
              <tr className={tw(`record-row ${quote.status === 'new' || (quote.status === 'quoted' && quote.order_status === 'pending') ? 'bg-warning-soft hover:bg-warning-soft' : ''}`)} key={quote.id} onDoubleClick={() => openQuote(quote)}>
                <td><button className={tw('record-link')} type="button" onClick={() => openQuote(quote)}>{quote.quote_number}</button></td>
                <td><div className={tw('quote-requester')}><strong>{quote.requester_contact_person}</strong><small>{quote.requester_company_name || quote.requester_email}</small></div></td>
                <td>{new Date(quote.created_at).toLocaleDateString()}</td>
                <td>{quote.items.reduce((total, item) => total + item.quantity, 0)}</td>
                <td>{quote.order_number || 'No order'}</td>
                <td><span className={tw(`status status-${quoteStatusKey(quote.status, quote.order_status)}`)}>{quoteStatusLabel(quote.status, quote.order_status)}</span></td>
                <td><button className={tw('table-action')} type="button" onClick={() => openQuote(quote)}>View</button></td>
              </tr>
            )) : <tr><td colSpan={7}>No quote requests found.</td></tr>}</tbody>
          </table>
        </div>
      </section>
      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={quoteTotal}
        loading={quotesQuery.isFetching}
        className="mt-3"
        onPageChange={setPage}
      />
      {selected ? (
        <div className={tw('editor-backdrop')} role="presentation" onMouseDown={closeQuote}>
          <aside className={tw('order-editor')} role="dialog" aria-modal="true" aria-labelledby="quote-details-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className={tw('panel-heading')}><div><p className={tw('eyebrow')}>QUOTE REQUEST</p><h2 id="quote-details-title">{selected.quote_number}</h2></div><button type="button" aria-label="Close quote details" onClick={closeQuote}><X /></button></div>
            <p>{selected.requester_contact_person}<br />{selected.requester_company_name ? <>{selected.requester_company_name}<br /></> : null}{selected.requester_email}<br />{selected.requester_phone}</p>
            {selected.status === 'new' ? <button className={tw('record-payment-link')} type="button" disabled={update.isPending} onClick={() => update.mutate({ quoteNumber: selected.quote_number, data: { status: 'reviewing' } })}>Start review</button> : null}
            <div className={tw('order-editor-items')}>{selected.items.map((item) => <div key={item.id}><div className={tw('record-item-main')}><ProductThumbnail imageUrl={item.image_url} name={item.product_name} /><span>{item.product_name}<small>{item.sku || 'Product'} · Qty {item.quantity}</small></span></div>{canEditInvoice ? <label className={tw('quote-price-input')}>Unit price{item.bulk_price_applied ? <small>Bulk price</small> : null}<input type="number" min="0.01" step="0.01" value={itemPrices[item.id] ?? item.quoted_unit_price ?? item.suggested_unit_price ?? ''} onChange={(event) => setItemPrices((current) => ({ ...current, [item.id]: event.target.value }))} /></label> : <strong>{invoiceSent && item.quoted_line_total ? `$${Number(item.quoted_line_total).toFixed(2)}` : `Qty ${item.quantity}`}</strong>}</div>)}</div>
            {selected.notes ? <p className={tw('quote-notes')}>{selected.notes}</p> : null}
            {canEditInvoice ? <div className="mt-5 flex w-full flex-row flex-nowrap items-center gap-2.5"><input id="request-additional-information" className="m-0 size-4 shrink-0 accent-brand" type="checkbox" checked={requestAdditionalInformation} onChange={(event) => setRequestAdditionalInformation(event.target.checked)} /><label htmlFor="request-additional-information" className="m-0 inline text-sm font-bold leading-5">Request additional information before sending an invoice</label></div> : null}
            {requestAdditionalInformation && (selected.status === 'reviewing' || (selected.status === 'quoted' && selected.order_status === 'pending')) ? <section className="mt-5 border-t border-border-soft pt-5"><h3 className="mb-3 flex items-center gap-2 text-sm font-extrabold"><MessageSquare size={17} />Review messages</h3><div ref={messagesRef} className="grid max-h-60 gap-2 overflow-y-auto rounded-control bg-surface-raised p-3" aria-live="polite">{selected.messages.length ? selected.messages.map((item) => <div className={item.sender_role === 'admin' ? 'ml-8 rounded-control bg-brand-soft p-3 text-sm' : 'mr-8 rounded-control border border-border bg-white p-3 text-sm'} key={item.id}><strong className="block text-xs">{item.author_name}</strong><p className="mt-1 whitespace-pre-wrap break-words text-text-subtle">{item.body}</p><small className="mt-1 block text-[10px] text-text-soft">{new Date(item.created_at).toLocaleString()}</small></div>) : <p className="text-sm text-text-soft">No messages yet. Send a message only if you need more information.</p>}</div><label className="mt-3 grid w-full gap-2 text-xs font-bold">Message<textarea ref={messageInputRef} rows={3} className="min-h-20 w-full resize-y overflow-y-auto rounded-control border border-border-input p-3 text-sm font-normal" value={message} onChange={(event) => setMessage(event.target.value)} /></label><button className={tw('record-payment-link')} type="button" disabled={!message.trim() || sendMessage.isPending} onClick={() => sendMessage.mutate()}><Send size={16} />Send message</button></section> : null}
            {canEditInvoice ? <div className={tw('quote-pricing-form')}><h3>{invoiceSent ? 'Revise invoice' : 'Invoice'}</h3><label>Shipping<input type="number" min="0" step="0.01" value={quotedShipping ?? selected.quoted_shipping ?? '0.00'} onChange={(event) => setQuotedShipping(event.target.value)} /></label><label>Invoice terms<textarea rows={3} value={adminMessage ?? selected.admin_message ?? ''} onChange={(event) => setAdminMessage(event.target.value)} placeholder="Validity, delivery timing and terms" /></label><button type="button" disabled={!canSendInvoice || invoice.isPending} onClick={sendInvoice}><FileText size={17} />{invoice.isPending ? 'Sending...' : invoiceSent ? 'Update and resend invoice' : 'Send invoice'}</button></div> : null}
            {invoiceSent ? <dl className={tw('record-totals')}><div><dt>Subtotal</dt><dd>${Number(selected.quoted_subtotal).toFixed(2)}</dd></div><div><dt>Shipping</dt><dd>${Number(selected.quoted_shipping).toFixed(2)}</dd></div><div><dt>Invoice total</dt><dd>${Number(selected.quoted_total).toFixed(2)}</dd></div></dl> : null}
            {selected.invoice_pdf_url ? <a className={`${tw('record-payment-link')} !text-white [&>svg]:text-white`} href={mediaUrl(selected.invoice_pdf_url)} target="_blank" rel="noreferrer"><Download size={17} />Download {selected.invoice_number}</a> : null}
            {selected.order_number ? <p>Invoice order: <strong>{selected.order_number}</strong></p> : <p>No order has been created from this quote.</p>}
            <StatusTimeline noun="Quote request" currentStatus={selected.status} initialStatus="new" createdAt={selected.created_at} updatedAt={selected.updated_at} steps={QUOTE_STEPS} />
            {selected.status !== 'approved' && selected.status !== 'quoted' && selected.status !== 'cancelled' ? (
              <div className={tw('quote-close-section')}>
                {!confirmingClose ? (
                  <button className={tw('quote-close-button')} type="button" onClick={() => setConfirmingClose(true)}><AlertTriangle size={17} />Cancel quote</button>
                ) : (
                  <div className={tw('quote-close-alert')} role="alertdialog" aria-labelledby="close-quote-title" aria-describedby="close-quote-description">
                    <AlertTriangle size={20} />
                    <div><strong id="close-quote-title">Cancel this quote?</strong><p id="close-quote-description">This ends the negotiation permanently. The quote cannot be reopened and no order will be created.</p></div>
                    <div><button type="button" onClick={() => setConfirmingClose(false)}>Keep negotiating</button><button type="button" onClick={() => update.mutate({ quoteNumber: selected.quote_number, data: { status: 'cancelled' } })} disabled={update.isPending}>Cancel quote</button></div>
                  </div>
                )}
              </div>
            ) : selected.status === 'cancelled' ? <p className={tw('quote-closed-note')}>This quote is cancelled and cannot be reopened.</p> : null}
          </aside>
        </div>
      ) : null}
    </main>
  )
}
