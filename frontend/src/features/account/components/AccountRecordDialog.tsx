import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CreditCard, Download, FileText, MessageSquare, Package, Send, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ProductThumbnail } from '../../../components/ProductThumbnail'
import { StatusTimeline } from '../../../components/StatusTimeline'
import { tw } from '../../../lib/tailwind-styles'
import { api, ApiError, mediaUrl } from '../../../lib/api'
import { orderSourceLabel, orderStatusKey, orderStatusLabel, quoteStatusKey, quoteStatusLabel } from '../../../lib/status-labels'
import type { Order, QuoteRequest } from '../../../types'

const orderSteps = [
  { value: 'pending', label: 'Pending' },
  { value: 'processing', label: 'Processing' },
  { value: 'completed', label: 'Completed' },
] as const

const quoteSteps = [
  { value: 'new', label: 'Pending' },
  { value: 'reviewing', label: 'Processing' },
  { value: 'quoted', label: 'Processing' },
  { value: 'approved', label: 'Completed' },
] as const

export type AccountRecord =
  | { kind: 'order'; value: Order }
  | { kind: 'quote'; value: QuoteRequest }

export function AccountRecordDialog({ record, onClose, onLinkedQuoteSelect, paymentsEnabled = false }: { record: AccountRecord; onClose: () => void; onLinkedQuoteSelect?: (quoteNumber: string) => void; paymentsEnabled?: boolean }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const isOrder = record.kind === 'order'
  const title = isOrder ? record.value.order_number : record.value.quote_number

  return (
    <div className={tw('modal-backdrop')} role="presentation" onMouseDown={onClose}>
      <section className={tw('account-record-dialog')} role="dialog" aria-modal="true" aria-labelledby="account-record-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className={tw('record-dialog-heading')}>
          <span>{isOrder ? <Package size={20} /> : <FileText size={20} />}</span>
          <div><p>{isOrder ? 'ORDER DETAILS' : 'QUOTE REQUEST'}</p><h2 id="account-record-title">{title}</h2></div>
          <button type="button" aria-label="Close details" onClick={onClose}><X size={21} /></button>
        </header>
        {isOrder ? <ClientOrderDetails order={record.value} paymentsEnabled={paymentsEnabled} onLinkedQuoteSelect={onLinkedQuoteSelect} /> : <ClientQuoteDetails initialQuote={record.value} paymentsEnabled={paymentsEnabled} />}
      </section>
    </div>
  )
}

function ClientOrderDetails({ order, paymentsEnabled, onLinkedQuoteSelect }: { order: Order; paymentsEnabled: boolean; onLinkedQuoteSelect?: (quoteNumber: string) => void }) {
  return (<>
    <div className={tw('record-summary')}>
      <div><span>Status</span><strong className={tw(`status status-${orderStatusKey(order.status)}`)}>{orderStatusLabel(order.status)}</strong></div>
      <div><span>Placed</span><strong>{new Date(order.created_at).toLocaleDateString()}</strong></div>
      <div><span>Order type</span><strong>{orderSourceLabel(order.source)}</strong></div>
      {order.quote_number ? <div><span>Quote</span><button className={tw('view-order')} type="button" onClick={() => onLinkedQuoteSelect?.(order.quote_number!)}>{order.quote_number}</button></div> : null}
    </div>
    <section className={tw('record-section')}>
      <h3>Items</h3>
      <div className={tw('record-items')}>{order.items.map((item) => (
        <div key={item.id}><div className={tw('record-item-main')}><ProductThumbnail imageUrl={item.image_url} name={item.product_name} /><span><strong>{item.product_name}</strong><small>{item.sku || 'Product'} · Qty {item.quantity}</small></span></div><strong>${Number(item.line_total).toFixed(2)}</strong></div>
      ))}</div>
      <dl className={tw('record-totals')}><div><dt>Subtotal</dt><dd>${Number(order.subtotal).toFixed(2)}</dd></div><div><dt>Shipping</dt><dd>${Number(order.shipping_fee).toFixed(2)}</dd></div><div><dt>Total</dt><dd>${Number(order.total).toFixed(2)}</dd></div></dl>
    </section>
    <section className={tw('record-section')}><h3>Delivery address</h3><p>{order.shipping_address}<br />{[order.shipping_city, order.shipping_state, order.shipping_postal_code].filter(Boolean).join(', ')}<br />{order.shipping_country}</p></section>
    {paymentsEnabled && order.status === 'pending' ? <Link className={tw('record-payment-link')} to={`/payment?order=${encodeURIComponent(order.order_number)}`}><CreditCard size={17} />Pay this order</Link> : null}
    {order.notes ? <section className={tw('record-section')}><h3>Notes</h3><p>{order.notes}</p></section> : null}
    <StatusTimeline noun="Order" currentStatus={orderStatusKey(order.status)} initialStatus="pending" createdAt={order.created_at} updatedAt={order.updated_at} steps={orderSteps} />
  </>)
}

function ClientQuoteDetails({ initialQuote, paymentsEnabled }: { initialQuote: QuoteRequest; paymentsEnabled: boolean }) {
  const queryClient = useQueryClient()
  const [message, setMessage] = useState('')
  const [confirmingCancel, setConfirmingCancel] = useState(false)
  const messagesRef = useRef<HTMLDivElement>(null)
  const messageInputRef = useRef<HTMLTextAreaElement>(null)
  const quoteQuery = useQuery({
    queryKey: ['quote', initialQuote.quote_number],
    queryFn: () => api.quote(initialQuote.quote_number),
    initialData: initialQuote,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  })
  const quote = quoteQuery.data
  useEffect(() => {
    const messageList = messagesRef.current
    if (messageList) messageList.scrollTop = messageList.scrollHeight
  }, [quote.messages])
  useEffect(() => {
    const input = messageInputRef.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(Math.max(input.scrollHeight, 80), 240)}px`
  }, [message])
  const applyQuote = (value: QuoteRequest, notice: string) => {
    queryClient.setQueryData(['quote', value.quote_number], value)
    queryClient.invalidateQueries({ queryKey: ['quotes', 'mine'] })
    setMessage('')
    toast.success(notice)
  }
  const sendMessage = useMutation({
    mutationFn: () => api.addQuoteMessage(quote.quote_number, message),
    onSuccess: (value) => applyQuote(value, 'Message sent.'),
    onError: (error) => toast.error(error instanceof ApiError ? error.message : 'Could not send the message'),
  })
  const cancelQuote = useMutation({
    mutationFn: () => api.cancelQuote(quote.quote_number),
    onSuccess: (value) => {
      applyQuote(value, 'Quote request cancelled')
      setConfirmingCancel(false)
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : 'Could not cancel the quote'),
  })
  const invoiceSent = Boolean(quote.invoiced_at && quote.quoted_total)
  return (<>
    <div className={tw('record-summary')}>
      <div><span>Status</span><strong className={tw(`status status-${quoteStatusKey(quote.status)}`)}>{quoteStatusLabel(quote.status)}</strong></div>
      <div><span>Submitted</span><strong>{new Date(quote.created_at).toLocaleDateString()}</strong></div>
      {quote.order_number ? <div><span>Order</span><strong>{quote.order_number}</strong></div> : null}
    </div>
    <section className={tw('record-section')}>
      <h3>{invoiceSent ? 'Invoiced items' : 'Requested items'}</h3>
      <div className={tw('record-items')}>{quote.items.map((item) => (
        <div key={item.id}><div className={tw('record-item-main')}><ProductThumbnail imageUrl={item.image_url} name={item.product_name} /><span><strong>{item.product_name}</strong><small>{item.sku || 'Product'} · Qty {item.quantity}{invoiceSent && item.quoted_unit_price ? ` at $${Number(item.quoted_unit_price).toFixed(2)}` : ''}</small></span></div><strong>{invoiceSent && item.quoted_line_total ? `$${Number(item.quoted_line_total).toFixed(2)}` : `Qty ${item.quantity}`}</strong></div>
      ))}</div>
      {invoiceSent ? <dl className={tw('record-totals')}><div><dt>Subtotal</dt><dd>${Number(quote.quoted_subtotal).toFixed(2)}</dd></div><div><dt>Shipping</dt><dd>${Number(quote.quoted_shipping).toFixed(2)}</dd></div><div><dt>Invoice total</dt><dd>${Number(quote.quoted_total).toFixed(2)}</dd></div></dl> : null}
    </section>
    <section className={tw('record-section')}><h3>Contact</h3><p>{quote.requester_contact_person}<br />{quote.requester_company_name ? <>{quote.requester_company_name}<br /></> : null}{quote.requester_email}{quote.requester_phone ? <><br />{quote.requester_phone}</> : null}</p></section>
    {quote.notes ? <section className={tw('record-section')}><h3>Notes</h3><p>{quote.notes}</p></section> : null}
    {invoiceSent && quote.admin_message ? <section className={tw('record-section')}><h3>Invoice terms</h3><p>{quote.admin_message}</p></section> : null}
    {quote.status === 'reviewing' || (quote.status === 'quoted' && quote.order_status === 'pending') ? <section className={tw('record-section')}><h3 className="flex items-center gap-2"><MessageSquare size={17} />Review messages</h3><div ref={messagesRef} className="grid max-h-64 gap-2 overflow-y-auto rounded-control bg-surface-raised p-3" aria-live="polite">{quote.messages.length ? quote.messages.map((item) => <div className={item.sender_role === 'customer' ? 'ml-8 rounded-control bg-brand-soft p-3 text-sm' : 'mr-8 rounded-control border border-border bg-white p-3 text-sm'} key={item.id}><strong className="block text-xs">{item.author_name}</strong><p className="mt-1 whitespace-pre-wrap break-words">{item.body}</p><small className="mt-1 block text-[10px] text-text-soft">{new Date(item.created_at).toLocaleString()}</small></div>) : <p>No messages yet.</p>}</div><label className="mt-3 grid w-full gap-2 text-xs font-bold">Message<textarea ref={messageInputRef} rows={3} className="min-h-20 w-full resize-y overflow-y-auto rounded-control border border-border-input p-3 text-sm font-normal" value={message} onChange={(event) => setMessage(event.target.value)} /></label><button className={tw('record-payment-link')} type="button" disabled={!message.trim() || sendMessage.isPending} onClick={() => sendMessage.mutate()}><Send size={16} />Send message</button></section> : null}
    {quote.status === 'quoted' && quote.invoice_pdf_url ? <section className={tw('record-section')}><h3>Invoice ready</h3><p>{quote.invoice_number} is ready for download and payment.</p><div className="flex flex-wrap gap-2"><a className={tw('record-payment-link')} href={mediaUrl(quote.invoice_pdf_url)} target="_blank" rel="noreferrer"><Download size={17} />Download PDF</a>{paymentsEnabled && quote.order_number ? <Link className={tw('record-payment-link')} to={`/payment?order=${encodeURIComponent(quote.order_number)}`}><CreditCard size={17} />Pay invoice</Link> : null}</div></section> : null}
    {quote.status === 'approved' && quote.order_number ? <Link className={tw('record-payment-link')} to="/account?tab=orders"><Package size={17} />View scheduled order</Link> : null}
    {quote.status === 'new' || quote.status === 'reviewing' ? <section className="mt-5 border-t border-border-soft pt-5">{!confirmingCancel ? <button className="inline-flex min-h-10 items-center gap-2 rounded-control border border-danger bg-white px-4 text-sm font-bold text-danger" type="button" onClick={() => setConfirmingCancel(true)}><AlertTriangle size={17} />Cancel quote request</button> : <div className={tw('quote-close-alert')} role="alertdialog" aria-labelledby="cancel-client-quote-title" aria-describedby="cancel-client-quote-description"><AlertTriangle size={20} /><div><strong id="cancel-client-quote-title">Cancel this quote request?</strong><p id="cancel-client-quote-description">This ends the negotiation permanently. The quote cannot be reopened.</p></div><div><button type="button" onClick={() => setConfirmingCancel(false)}>Keep negotiating</button><button type="button" disabled={cancelQuote.isPending} onClick={() => cancelQuote.mutate()}>{cancelQuote.isPending ? 'Cancelling...' : 'Cancel quote'}</button></div></div>}</section> : null}
    <StatusTimeline noun="Quote request" currentStatus={quote.status} initialStatus="new" createdAt={quote.created_at} updatedAt={quote.updated_at} steps={quoteSteps} />
  </>)
}
