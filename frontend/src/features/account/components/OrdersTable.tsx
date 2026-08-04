import { tw } from '../../../lib/tailwind-styles'
import type { Order } from '../../../types'

export function OrdersTable({
  orders,
  loading = false,
}: {
  orders: Order[];
  loading?: boolean;
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
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={4}>Loading orders...</td>
            </tr>
          ) : orders.length ? (
            orders.map((order) => (
              <tr key={order.id}>
                <td>{order.order_number}</td>
                <td>{new Date(order.created_at).toLocaleDateString()}</td>
                <td>
                  <span className={tw(`status status-${order.status}`)}>
                    {order.status}
                  </span>
                </td>
                <td>${Number(order.total).toFixed(2)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={4}>No orders yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

