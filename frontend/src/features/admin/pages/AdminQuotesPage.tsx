import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, BadgeCheck, Clock3, Download, FileText, Search, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { QuoteRequest } from '../../../types'
import { AdminErrorState } from '../components/AdminErrorState'
import { AdminSelect } from '../components/AdminSelect'
import { Metric } from '../components/Metric'
import { exportCsv } from '../utils/exportCsv'

const statusLabels: Record<QuoteRequest['status'], string> = {
  new: 'New',
  reviewing: 'Reviewing',
  quoted: 'Awaiting approval',
  approved: 'Approved to order',
  closed: 'Closed',
}

const statusTransitions: Record<QuoteRequest['status'], QuoteRequest['status'][]> = {
  new: ['new', 'reviewing'],
  reviewing: ['reviewing', 'quoted'],
  quoted: ['quoted', 'approved'],
  approved: ['approved'],
  closed: ['closed'],
}

export function AdminQuotesPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<QuoteRequest | null>(null)
  const [confirmingClose, setConfirmingClose] = useState(false)
  const quotesQuery = useQuery({ queryKey: ['admin-quotes'], queryFn: () => api.quotes('ordering=-created_at&page_size=100') })
  const allQuotes = quotesQuery.data ? unwrap(quotesQuery.data) : []
  const quotes = allQuotes.filter((quote) =>
    (!search || `${quote.quote_number} ${quote.requester_contact_person} ${quote.requester_company_name} ${quote.requester_email}`.toLowerCase().includes(search.toLowerCase())) &&
    (!status || quote.status === status),
  )
  const update = useMutation({
    mutationFn: ({ quoteNumber, value }: { quoteNumber: string; value: QuoteRequest['status'] }) => api.updateQuote(quoteNumber, value),
    onSuccess: (value) => {
      queryClient.invalidateQueries({ queryKey: ['admin-quotes'] })
      setSelected((current) => current ? { ...current, status: value.status, order_number: value.order_number } : null)
      setConfirmingClose(false)
      toast.success(value.status === 'closed' ? 'Quote closed' : 'Quote request updated')
    },
    onError: () => toast.error('Could not update the quote request'),
  })

  if (quotesQuery.isError) return <AdminErrorState resource="quote requests" />

  return (
    <main className={tw('admin-page')}>
      <div className={tw('admin-title-row')}>
        <div><p className={tw('admin-breadcrumb')}>Workspace / Quotes</p><h1>Quote requests</h1><p>Review customer requirements, confirm availability and prepare pricing.</p></div>
        <button type="button" onClick={() => exportCsv('digital-ptt-quotes.csv', quotes)}><Download size={18} />Export</button>
      </div>
      <section className={tw('admin-stats order-stats')}>
        <Metric label="Total requests" value={String(allQuotes.length)} icon={FileText} />
        <Metric label="New" value={String(allQuotes.filter((quote) => quote.status === 'new').length)} icon={Clock3} />
        <Metric label="Reviewing" value={String(allQuotes.filter((quote) => quote.status === 'reviewing').length)} icon={Search} />
        <Metric label="Approved orders" value={String(allQuotes.filter((quote) => quote.status === 'approved').length)} icon={BadgeCheck} />
      </section>
      <section className={tw('admin-panel admin-section-gap')}>
        <div className={tw('orders-toolbar')}>
          <h2>Recent requests</h2>
          <div><Search size={18} /><input placeholder="Search quote or customer" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
          <AdminSelect aria-label="Filter by quote status" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All status</option><option value="new">New</option><option value="reviewing">Reviewing</option><option value="quoted">Awaiting approval</option><option value="approved">Approved to order</option><option value="closed">Closed</option>
          </AdminSelect>
        </div>
        <div className={tw('admin-table-wrap')}>
          <table className={tw('admin-table')}>
            <thead><tr><th>Quote ID</th><th>Requester</th><th>Date</th><th>Items</th><th>Linked order</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>{quotes.length ? quotes.map((quote) => (
              <tr key={quote.id}>
                <td><strong>{quote.quote_number}</strong></td>
                <td><div className={tw('quote-requester')}><strong>{quote.requester_contact_person}</strong><small>{quote.requester_company_name || quote.requester_email}</small></div></td>
                <td>{new Date(quote.created_at).toLocaleDateString()}</td>
                <td>{quote.items.reduce((total, item) => total + item.quantity, 0)}</td>
                <td>{quote.order_number || 'Not approved'}</td>
                <td><span className={tw(`status status-${quote.status}`)}>{statusLabels[quote.status]}</span></td>
                <td><button className={tw('view-order')} type="button" onClick={() => { setConfirmingClose(false); setSelected(quote) }}>View</button></td>
              </tr>
            )) : <tr><td colSpan={7}>No quote requests found.</td></tr>}</tbody>
          </table>
        </div>
      </section>
      {selected ? (
        <div className={tw('editor-backdrop')} role="presentation" onMouseDown={() => setSelected(null)}>
          <aside className={tw('order-editor')} role="dialog" aria-modal="true" aria-labelledby="quote-details-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className={tw('panel-heading')}><div><p className={tw('eyebrow')}>QUOTE REQUEST</p><h2 id="quote-details-title">{selected.quote_number}</h2></div><button type="button" aria-label="Close quote details" onClick={() => setSelected(null)}><X /></button></div>
            <p>{selected.requester_contact_person}<br />{selected.requester_company_name ? <>{selected.requester_company_name}<br /></> : null}{selected.requester_email}<br />{selected.requester_phone}</p>
            <div className={tw('order-editor-items')}>{selected.items.map((item) => <div key={item.id}><span>{item.product_name}</span><strong>x {item.quantity}</strong></div>)}</div>
            {selected.notes ? <p className={tw('quote-notes')}>{selected.notes}</p> : null}
            {selected.order_number ? <p>Linked order: <strong>{selected.order_number}</strong></p> : <p>No order has been created. Move the quote through review, then choose <strong>Approved to order</strong>.</p>}
            <label>Quote status<AdminSelect value={selected.status} onChange={(event) => update.mutate({ quoteNumber: selected.quote_number, value: event.target.value as QuoteRequest['status'] })}>{statusTransitions[selected.status].map((value) => <option value={value} key={value}>{statusLabels[value]}</option>)}</AdminSelect></label>
            {selected.status !== 'approved' && selected.status !== 'closed' ? (
              <div className={tw('quote-close-section')}>
                {!confirmingClose ? (
                  <button className={tw('quote-close-button')} type="button" onClick={() => setConfirmingClose(true)}><AlertTriangle size={17} />Close quote</button>
                ) : (
                  <div className={tw('quote-close-alert')} role="alertdialog" aria-labelledby="close-quote-title" aria-describedby="close-quote-description">
                    <AlertTriangle size={20} />
                    <div><strong id="close-quote-title">Close this quote?</strong><p id="close-quote-description">This is permanent. The quote cannot be reopened and no order will be created.</p></div>
                    <div><button type="button" onClick={() => setConfirmingClose(false)}>Cancel</button><button type="button" onClick={() => update.mutate({ quoteNumber: selected.quote_number, value: 'closed' })} disabled={update.isPending}>Confirm close</button></div>
                  </div>
                )}
              </div>
            ) : selected.status === 'closed' ? <p className={tw('quote-closed-note')}>This quote is closed and cannot be reopened.</p> : null}
          </aside>
        </div>
      ) : null}
    </main>
  )
}
