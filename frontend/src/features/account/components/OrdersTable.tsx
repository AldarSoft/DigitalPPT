import { Link } from 'react-router-dom'
import { CreditCard } from 'lucide-react'
import { tw } from '../../../lib/tailwind-styles'
import { orderSourceLabel, orderStatusKey, orderStatusLabel } from '../../../lib/status-labels'
import type { Order } from '../../../types'

export function OrdersTable({
  orders,
  loading = false,
  onSelect,
  paymentsEnabled = false,
  organizationId = null,
}: {
  orders: Order[];
  loading?: boolean;
  onSelect?: (order: Order) => void;
  paymentsEnabled?: boolean;
  organizationId?: number | null;
}) {
  return (
    <div className={tw("responsive-table")}>
      <table>
        <thead>
          <tr>
            <th>Order</th>
            <th>Order type</th>
            <th>Date</th>
            <th>Status</th>
            <th>Total</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={6}>Loading orders...</td>
            </tr>
          ) : orders.length ? (
            orders.map((order) => (
              <tr className={tw(`record-row ${order.status === 'pending' && order.source === 'quote' ? 'bg-warning-soft hover:bg-warning-soft' : ''}`)} key={order.id} onDoubleClick={() => onSelect?.(order)}>
                <td><span className={tw('mobile-table-label')}>Order</span><button className={tw('record-link')} type="button" onClick={() => onSelect?.(order)}>{order.order_number}</button></td>
                <td><span className={tw('mobile-table-label')}>Order type</span><span>{orderSourceLabel(order.source)}</span></td>
                <td><span className={tw('mobile-table-label')}>Date</span><span>{new Date(order.created_at).toLocaleDateString()}</span></td>
                <td>
                  <span className={tw('mobile-table-label')}>Status</span>
                  <span className={tw(`status status-${orderStatusKey(order.status)}`)}>
                    {orderStatusLabel(order.status, order.source)}
                  </span>
                </td>
                <td><span className={tw('mobile-table-label')}>Total</span><strong>${Number(order.total).toFixed(2)}</strong></td>
                <td><span className={tw('mobile-table-label')}>Action</span><div className={tw('account-order-actions')}><button className={tw('table-action')} type="button" onClick={() => onSelect?.(order)}>View</button>{paymentsEnabled && order.status === 'pending' ? <Link className={tw('account-pay-now')} to={`/payment?order=${encodeURIComponent(order.order_number)}${organizationId ? `&org=${organizationId}` : ''}`}><CreditCard size={15} />Pay now</Link> : null}</div></td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={6}>No orders yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
