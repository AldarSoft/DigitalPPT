import { Link } from 'react-router-dom'
import { tw } from '../../../lib/tailwind-styles'
import type { Order } from '../../../types'

export function OrdersTable({
  orders,
  loading = false,
  onSelect,
  paymentsEnabled = false,
}: {
  orders: Order[];
  loading?: boolean;
  onSelect?: (order: Order) => void;
  paymentsEnabled?: boolean;
}) {
  return (
    <div className={tw("responsive-table")}>
      <table>
        <thead>
          <tr>
            <th>Order</th>
            <th>Date</th>
            <th>Status</th>
            <th>Total</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={5}>Loading orders...</td>
            </tr>
          ) : orders.length ? (
            orders.map((order) => (
              <tr className={tw('record-row')} key={order.id} onDoubleClick={() => onSelect?.(order)}>
                <td>{order.order_number}</td>
                <td>{new Date(order.created_at).toLocaleDateString()}</td>
                <td>
                  <span className={tw(`status status-${order.status}`)}>
                    {order.status}
                  </span>
                </td>
                <td>${Number(order.total).toFixed(2)}</td>
                <td><div className={tw('account-order-actions')}><button className={tw('view-order')} type="button" onClick={() => onSelect?.(order)}>View</button>{paymentsEnabled && order.status === 'pending' ? <Link to={`/payment?order=${encodeURIComponent(order.order_number)}`}>Pay now</Link> : null}</div></td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={5}>No orders yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
