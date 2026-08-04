import { tw } from '../../../lib/tailwind-styles'
import type { QuoteRequest } from '../../../types'

const statusLabels: Record<QuoteRequest['status'], string> = {
  new: 'New',
  reviewing: 'Reviewing',
  quoted: 'Awaiting approval',
  approved: 'Approved to order',
  closed: 'Closed',
}

export function QuotesTable({ quotes, loading = false }: { quotes: QuoteRequest[]; loading?: boolean }) {
  return (
    <div className={tw('responsive-table')}>
      <table>
        <thead><tr><th>Quote request</th><th>Date</th><th>Items</th><th>Status</th></tr></thead>
        <tbody>
          {loading ? <tr><td colSpan={4}>Loading quote requests...</td></tr> : quotes.length ? quotes.map((quote) => (
            <tr key={quote.id}>
              <td>{quote.quote_number}</td>
              <td>{new Date(quote.created_at).toLocaleDateString()}</td>
              <td>{quote.items.reduce((total, item) => total + item.quantity, 0)}</td>
              <td><span className={tw(`status status-${quote.status}`)}>{statusLabels[quote.status]}</span></td>
            </tr>
          )) : <tr><td colSpan={4}>No quote requests yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
