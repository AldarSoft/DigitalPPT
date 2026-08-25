import { tw } from '../../../lib/tailwind-styles'
import { quoteStatusKey, quoteStatusLabel } from '../../../lib/status-labels'
import type { QuoteRequest } from '../../../types'

export function QuotesTable({ quotes, loading = false, onSelect }: { quotes: QuoteRequest[]; loading?: boolean; onSelect?: (quote: QuoteRequest) => void }) {
  return (
    <div className={tw('responsive-table')}>
      <table>
        <thead><tr><th>Quote request</th><th>Date</th><th>Items</th><th>Quoted total</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>
          {loading ? <tr><td colSpan={6}>Loading quote requests...</td></tr> : quotes.length ? quotes.map((quote) => (
            <tr className={tw('record-row')} key={quote.id} onDoubleClick={() => onSelect?.(quote)}>
              <td><span className={tw('mobile-table-label')}>Quote request</span><button className={tw('record-link')} type="button" onClick={() => onSelect?.(quote)}>{quote.quote_number}</button></td>
              <td><span className={tw('mobile-table-label')}>Date</span><span>{new Date(quote.created_at).toLocaleDateString()}</span></td>
              <td><span className={tw('mobile-table-label')}>Items</span><span>{quote.items.reduce((total, item) => total + item.quantity, 0)}</span></td>
              <td><span className={tw('mobile-table-label')}>Quoted total</span><strong>{quote.quoted_total ? `$${Number(quote.quoted_total).toFixed(2)}` : 'Pending'}</strong></td>
              <td><span className={tw('mobile-table-label')}>Status</span><span className={tw(`status status-${quoteStatusKey(quote.status)}`)}>{quoteStatusLabel(quote.status)}</span></td>
              <td><span className={tw('mobile-table-label')}>Action</span><button className={tw('table-action')} type="button" onClick={() => onSelect?.(quote)}>View</button></td>
            </tr>
          )) : <tr><td colSpan={6}>No quote requests yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
