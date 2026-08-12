import { Boxes, FileText, Package, Search } from 'lucide-react'
import { tw } from '../../../lib/tailwind-styles'
import type { QuoteRequest, User } from '../../../types'
import type { AccountTab } from '../types'
import { QuotesTable } from './QuotesTable'

export function AccountOverview({
  user,
  quotes,
  orderCount,
  quoteCount,
  onTab,
  onQuoteSelect,
}: {
  user: User;
  quotes: QuoteRequest[];
  orderCount: number;
  quoteCount: number;
  onTab: (tab: AccountTab) => void;
  onQuoteSelect: (quote: QuoteRequest) => void;
}) {
  const inReview = quotes.filter((quote) => quote.status === 'new' || quote.status === 'reviewing').length;
  return (
    <>
      <div className={tw("account-stats")}>
        <article>
          <FileText size={23} />
          <strong>{quoteCount}</strong>
          <span>Quote requests</span>
        </article>
        <article>
          <Search size={23} />
          <strong>{inReview}</strong>
          <span>In review</span>
        </article>
        <article>
          <Package size={23} />
          <strong>{orderCount}</strong>
          <span>Past orders</span>
        </article>
      </div>
      <section className={tw("account-panel")}>
        <div className={tw("panel-title")}>
          <h2>Recent quote requests</h2>
          <button type="button" onClick={() => onTab('quotes')}>
            View all requests
          </button>
        </div>
        <QuotesTable quotes={quotes.slice(0, 4)} onSelect={onQuoteSelect} />
      </section>
      <div className={tw("account-detail-grid")}>
        <section className={tw("account-panel")}>
          <h2>Default address</h2>
          <p>
            {user.first_name} {user.last_name}
            <br />
            {user.profile.address_line_1 || "No address saved"}
            <br />
            {[user.profile.city, user.profile.state, user.profile.postal_code]
              .filter(Boolean)
              .join(", ")}
          </p>
          <button type="button" onClick={() => onTab("addresses")}>
            Edit address
          </button>
        </section>
        <section className={tw("account-panel")}>
          <h2>Account type</h2>
          <div className={tw("account-type")}>
            <Boxes size={24} />
            <span>
              <strong>
                {user.is_staff ? "Staff administrator" : "Customer account"}
              </strong>
              <small>
                {user.profile.company_name || "Digital PTT customer"}
              </small>
            </span>
          </div>
        </section>
      </div>
    </>
  );
}
