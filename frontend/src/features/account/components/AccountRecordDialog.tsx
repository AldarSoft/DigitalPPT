import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CreditCard, Download, FileText, MessageSquare, Package, Send, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ProductThumbnail } from '../../../components/ProductThumbnail'
import { StatusTimeline } from '../../../components/StatusTimeline'
import { tw } from '../../../lib/tailwind-styles'
import { api, ApiError } from '../../../lib/api'
import { orderSourceLabel, orderStatusKey, orderStatusLabel, quoteStatusKey, quoteStatusLabel } from '../../../lib/status-labels'
import type { Order, QuoteRequest } from '../../../types'

const orderSteps = [
  { value: 'pending', label: 'Pending' },
  { value: 'processing', label: 'Processing' },
  { value: 'completed', label: 'Completed' },
] as const

const quoteSteps = [
  { value: 'new', label: 'Pending review' },
  { value: 'reviewing', label: 'In review' },
  { value: 'quote_approved', label: 'Quote approved' },
  { value: 'invoice_sent', label: 'Invoice sent' },
  { value: 'awaiting_payment', label: 'Awaiting payment' },
  { value: 'payment_confirmed', label: 'Payment confirmed' },
] as const

export type AccountRecord =
  | { kind: 'order'; value: Order }
  | { kind: 'quote'; value: QuoteRequest }

export function AccountRecordDialog({ record, onClose, onLinkedQuoteSelect, paymentsEnabled = false, bankTransferEnabled = false, organizationId = null }: { record: AccountRecord; onClose: () => void; onLinkedQuoteSelect?: (quoteNumber: string) => void; paymentsEnabled?: boolean; bankTransferEnabled?: boolean; organizationId?: number | null }) {
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
        {isOrder ? <ClientOrderDetails order={record.value} organizationId={organizationId} paymentsEnabled={paymentsEnabled} onLinkedQuoteSelect={onLinkedQuoteSelect} /> : <ClientQuoteDetails initialQuote={record.value} organizationId={organizationId} paymentsEnabled={paymentsEnabled} bankTransferEnabled={bankTransferEnabled} />}
      </section>
    </div>
  )
}

function ClientOrderDetails({ order, paymentsEnabled, onLinkedQuoteSelect, organizationId }: { order: Order; paymentsEnabled: boolean; onLinkedQuoteSelect?: (quoteNumber: string) => void; organizationId: number | null }) {
  return (<>
    <div className={tw('record-summary')}>
      <div><span>Status</span><strong className={tw(`status status-${orderStatusKey(order.status)}`)}>{orderStatusLabel(order.status, order.source)}</strong></div>
      <div><span>Placed</span><strong>{new Date(order.created_at).toLocaleDateString()}</strong></div>
      <div><span>Order type</span><strong>{orderSourceLabel(order.source)}</strong></div>
      {order.quote_number ? <div><span>Quote</span><button className={tw('view-order')} type="button" onClick={() => onLinkedQuoteSelect?.(order.quote_number!)}>{order.quote_number}</button></div> : null}
    </div>
    <section className={tw('record-section')}>
      <h3>Items</h3>
      <div className={tw('record-items')}>{order.items.map((item) => (
        <div key={item.id}><div className={tw('record-item-main')}><ProductThumbnail imageUrl={item.image_url} name={item.product_name} /><span><strong>{item.product_name}</strong><small>{item.sku || 'Product'} · Qty {item.quantity}</small>{item.fulfillment_status !== 'not_required' ? <small className={item.backordered_quantity ? 'text-warning' : 'text-success'}>{item.backordered_quantity ? `${item.reserved_quantity} reserved · ${item.backordered_quantity} awaiting stock` : `${item.reserved_quantity} ready to ship`}</small> : null}</span></div><strong>${Number(item.line_total).toFixed(2)}</strong></div>
      ))}</div>
      <dl className={tw('record-totals')}><div><dt>Subtotal</dt><dd>${Number(order.subtotal).toFixed(2)}</dd></div><div><dt>Shipping</dt><dd>${Number(order.shipping_fee).toFixed(2)}</dd></div><div><dt>Total</dt><dd>${Number(order.total).toFixed(2)}</dd></div></dl>
    </section>
    <section className={tw('record-section')}><h3>Delivery address</h3><p>{order.shipping_address}<br />{[order.shipping_city, order.shipping_state, order.shipping_postal_code].filter(Boolean).join(', ')}<br />{order.shipping_country}</p></section>
    {order.shipments && order.shipments.length ? <section className={tw('record-section')}><h3>Shipments</h3><div className="grid gap-2">{order.shipments.map((shipment) => (
      <div key={shipment.id} className="rounded-control border border-border p-3 text-sm">
        <div className="flex items-center justify-between gap-2"><strong>{shipment.shipment_number}</strong><small className="text-text-soft">{new Date(shipment.shipped_at).toLocaleDateString()}</small></div>
        <p className="mt-1 text-xs text-text-soft">{shipment.carrier || 'Courier'}{shipment.tracking_number ? <span> · Tracking: {shipment.tracking_number}</span> : null}</p>
        <ul className="mt-1 text-xs">{shipment.items.map((line) => <li key={line.id}>{line.product_name} × {line.quantity}</li>)}</ul>
      </div>
    ))}</div></section> : null}
    {paymentsEnabled && order.status === 'pending' ? <Link className={tw('record-payment-link')} to={`/payment?order=${encodeURIComponent(order.order_number)}${organizationId ? `&org=${organizationId}` : ''}`}><CreditCard size={17} />Pay this order</Link> : null}
    {order.notes ? <section className={tw('record-section')}><h3>Notes</h3><p>{order.notes}</p></section> : null}
    <StatusTimeline noun="Order" currentStatus={orderStatusKey(order.status)} initialStatus="pending" createdAt={order.created_at} updatedAt={order.updated_at} steps={orderSteps} />
  </>)
}

function ClientQuoteDetails({ initialQuote, paymentsEnabled, bankTransferEnabled, organizationId }: { initialQuote: QuoteRequest; paymentsEnabled: boolean; bankTransferEnabled: boolean; organizationId: number | null }) {
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
  const downloadInvoice = useMutation({
    mutationFn: () => api.downloadQuoteInvoice(quote.quote_number, quote.invoice_number || quote.quote_number),
    onError: (error) => toast.error(error instanceof ApiError ? error.message : 'Could not download the invoice'),
  })
  const invoiceSent = Boolean(quote.invoiced_at && quote.quoted_total)
  const canDiscussQuote = ['reviewing', 'quote_approved', 'invoice_sent', 'awaiting_payment', 'payment_rejected'].includes(quote.status)
  const invoiceAwaitingPayment = ['invoice_sent', 'awaiting_payment', 'payment_rejected'].includes(quote.status)
  return (<>
    <div className={tw('record-summary')}>
      <div><span>Status</span><strong className={tw(`status status-${quoteStatusKey(quote.status, quote.order_status)}`)}>{quoteStatusLabel(quote.status, quote.order_status)}</strong></div>
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
    {canDiscussQuote ? <section className={tw('record-section')}><h3 className="flex items-center gap-2"><MessageSquare size={17} />Review messages</h3><div ref={messagesRef} className="grid max-h-64 gap-2 overflow-y-auto rounded-control bg-surface-raised p-3" aria-live="polite">{quote.messages.length ? quote.messages.map((item) => <div className={item.sender_role === 'customer' ? 'ml-8 rounded-control bg-brand-soft p-3 text-sm' : 'mr-8 rounded-control border border-border bg-white p-3 text-sm'} key={item.id}><strong className="block text-xs">{item.author_name}</strong><p className="mt-1 whitespace-pre-wrap break-words">{item.body}</p><small className="mt-1 block text-[10px] text-text-soft">{new Date(item.created_at).toLocaleString()}</small></div>) : <p>No messages yet.</p>}</div><label className="mt-3 grid w-full gap-2 text-xs font-bold">Message<textarea ref={messageInputRef} rows={3} className="min-h-20 w-full resize-y overflow-y-auto rounded-control border border-border-input p-3 text-sm font-normal" value={message} onChange={(event) => setMessage(event.target.value)} /></label><button className={tw('record-payment-link')} type="button" disabled={!message.trim() || sendMessage.isPending} onClick={() => sendMessage.mutate()}><Send size={16} />Send message</button></section> : null}
    {quote.status === 'payment_rejected' ? <section className="mt-5 rounded-control border border-danger bg-danger-soft p-4 text-sm text-danger"><h3 className="text-base font-extrabold text-ink">Payment needs correction</h3><p className="mt-1">{quote.payment_rejection_reason || 'The bank transfer could not be matched. Contact Digital PTT before sending another transfer.'}</p><p className="mt-2 text-text-subtle">Your invoice remains unpaid.</p></section> : null}
    {invoiceAwaitingPayment && quote.invoice_pdf_url ? <section className="mt-5 rounded-control border border-warning bg-warning-soft p-4 text-sm text-warning"><h3 className="text-base font-extrabold text-ink">Invoice ready for payment</h3><p className="mt-1">{quote.invoice_number} created order {quote.order_number || 'for this quote'} and is waiting for payment.</p>{bankTransferEnabled ? <p className="mt-2 text-ink">Pay through your bank using the invoice number as the required transfer reference. Payment is confirmed after Digital PTT reconciles the transfer.</p> : null}<div className="mt-3 flex flex-wrap gap-2"><button className={`${tw('record-payment-link')} !text-white [&>svg]:text-white`} type="button" disabled={downloadInvoice.isPending} onClick={() => downloadInvoice.mutate()}><Download size={17} />{downloadInvoice.isPending ? 'Downloading...' : 'Download PDF'}</button>{paymentsEnabled && quote.order_number ? <Link className={`${tw('record-payment-link')} !text-white [&>svg]:text-white`} to={`/payment?order=${encodeURIComponent(quote.order_number)}${organizationId ? `&org=${organizationId}` : ''}`}><CreditCard size={17} />Pay invoice</Link> : null}</div></section> : null}
    {quote.status === 'payment_confirmed' && quote.order_number ? <Link className={tw('record-payment-link')} to="/account?tab=orders"><Package size={17} />View fulfillment status</Link> : null}
    {['new', 'reviewing', 'quote_approved'].includes(quote.status) ? <section className="mt-5 border-t border-border-soft pt-5">{!confirmingCancel ? <button className="inline-flex min-h-10 items-center gap-2 rounded-control border border-danger bg-white px-4 text-sm font-bold text-danger" type="button" onClick={() => setConfirmingCancel(true)}><AlertTriangle size={17} />Cancel quote request</button> : <div className={tw('quote-close-alert')} role="alertdialog" aria-labelledby="cancel-client-quote-title" aria-describedby="cancel-client-quote-description"><AlertTriangle size={20} /><div><strong id="cancel-client-quote-title">Cancel this quote request?</strong><p id="cancel-client-quote-description">This ends the negotiation permanently. The quote cannot be reopened.</p></div><div><button type="button" onClick={() => setConfirmingCancel(false)}>Keep negotiating</button><button type="button" disabled={cancelQuote.isPending} onClick={() => cancelQuote.mutate()}>{cancelQuote.isPending ? 'Cancelling...' : 'Cancel quote'}</button></div></div>}</section> : null}
    <StatusTimeline noun="Quote request" currentStatus={quote.status} initialStatus="new" createdAt={quote.created_at} updatedAt={quote.updated_at} steps={quoteSteps} />
  </>)
}
