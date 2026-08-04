import { tw } from '../../../lib/tailwind-styles'
import type { Order } from '../../../types'

export function OrderRows({ orders, compact = false, onSelect }: {
    orders: Order[];
    compact?: boolean;
    onSelect?: (order: Order) => void;
}) {
    return (<div className={tw("admin-table-wrap")}>
      <table className={tw(`admin-table ${compact ? 'admin-table-compact' : ''}`)}>
        <thead><tr><th>Order ID</th><th>Customer</th><th>Date</th><th>Total</th><th>Status</th>{compact ? null : <th>Action</th>}</tr></thead>
        <tbody>{orders.length ? orders.map((order) => (<tr key={order.id}><td><strong>{order.order_number}</strong></td><td>{order.customer_first_name} {order.customer_last_name}</td><td>{new Date(order.created_at).toLocaleDateString()}</td><td>${Number(order.total).toFixed(2)}</td><td><span className={tw(`status status-${order.status}`)}>{order.status}</span></td>{compact ? null : <td><button className={tw("view-order")} type="button" onClick={() => onSelect?.(order)}>View</button></td>}</tr>)) : <tr><td colSpan={compact ? 5 : 6}>No orders found.</td></tr>}</tbody>
      </table>
    </div>);
}

