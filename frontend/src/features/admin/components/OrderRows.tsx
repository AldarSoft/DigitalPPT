import { tw } from '../../../lib/tailwind-styles'
import { orderSourceLabel, orderStatusKey, orderStatusLabel } from '../../../lib/status-labels'
import type { Order } from '../../../types'

export function OrderRows({ orders, compact = false, onSelect }: {
    orders: Order[];
    compact?: boolean;
    onSelect?: (order: Order) => void;
}) {
    return (<div className={tw("admin-table-wrap")}>
      <table className={tw(`admin-table ${compact ? 'admin-table-compact' : ''}`)}>
        <thead><tr><th>Order ID</th><th>Order type</th><th>Customer</th><th>Date</th><th>Total</th><th>Status</th>{compact ? null : <th>Action</th>}</tr></thead>
        <tbody>{orders.length ? orders.map((order) => (<tr className={tw(`record-row ${order.status === 'pending' && order.source === 'quote' ? 'bg-warning-soft hover:bg-warning-soft' : ''}`)} key={order.id} onDoubleClick={() => onSelect?.(order)}><td><button className={tw('record-link')} type="button" onClick={() => onSelect?.(order)}>{order.order_number}</button></td><td>{orderSourceLabel(order.source)}</td><td>{order.customer_first_name} {order.customer_last_name}</td><td>{new Date(order.created_at).toLocaleDateString()}</td><td>${Number(order.total).toFixed(2)}</td><td><span className={tw(`status status-${orderStatusKey(order.status)}`)}>{orderStatusLabel(order.status, order.source)}</span></td>{compact ? null : <td><button className={tw('table-action')} type="button" onClick={() => onSelect?.(order)}>View</button></td>}</tr>)) : <tr><td colSpan={compact ? 6 : 7}>No orders found.</td></tr>}</tbody>
      </table>
    </div>);
}
