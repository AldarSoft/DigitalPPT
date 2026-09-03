import { Boxes, FileText, Gauge, Package, RadioTower, Search } from 'lucide-react'
import { tw } from '../../../lib/tailwind-styles'
import type { QuoteRequest, User } from '../../../types'
import type { AccountTab } from '../types'
import type { OrganizationLicenseSummary } from '../../licensing/types'
import { QuotesTable } from './QuotesTable'

export function AccountOverview({
  user,
  quotes,
  orderCount,
  quoteCount,
  licenseSummary,
  onTab,
  onQuoteSelect,
}: {
  user: User;
  quotes: QuoteRequest[];
  orderCount: number;
  quoteCount: number;
  licenseSummary?: OrganizationLicenseSummary;
  onTab: (tab: AccountTab) => void;
  onQuoteSelect: (quote: QuoteRequest) => void;
}) {
  const needsAttention = quotes.filter((quote) => (
    quote.status === 'new'
    || quote.status === 'reviewing'
    || quote.status === 'quote_approved'
    || quote.status === 'invoice_sent'
    || quote.status === 'awaiting_payment'
    || quote.status === 'payment_rejected'
  )).length;
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
          <strong>{needsAttention}</strong>
          <span>Needs attention</span>
        </article>
        <article>
          <Package size={23} />
          <strong>{orderCount}</strong>
          <span>Orders</span>
        </article>
        <article>
          <RadioTower size={23} />
          <strong>{licenseSummary?.licensed_product_quantity ?? 0}</strong>
          <span>Licensed radios across {licenseSummary?.licensed_product_count ?? 0} product types</span>
        </article>
        <article>
          <Gauge size={23} />
          <strong>{licenseSummary?.usable_license_capacity ?? 0}</strong>
          <span>Usable license capacity</span>
        </article>
      </div>
      <section className={tw("account-panel")}>
        <div className={tw("panel-title")}>
          <h2>Recent quote requests</h2>
          <button className={tw('action-button action-button-secondary action-button-compact')} type="button" onClick={() => onTab('quotes')}>
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
          <button className={tw('action-button action-button-secondary action-button-compact mt-3')} type="button" onClick={() => onTab("settings")}>
            Edit account settings
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
