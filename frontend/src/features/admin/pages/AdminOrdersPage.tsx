import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Boxes, Download, Package, Search, ShoppingCart, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { Order } from '../../../types'
import { AdminSelect } from '../components/AdminSelect'
import { AdminErrorState } from '../components/AdminErrorState'
import { Metric } from '../components/Metric'
import { OrderRows } from '../components/OrderRows'
import { exportCsv } from '../utils/exportCsv'

export function AdminOrdersPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [status, setStatus] = useState('');
    const [selected, setSelected] = useState<Order | null>(null);
    const ordersQuery = useQuery({ queryKey: ['admin-orders'], queryFn: () => api.orders('ordering=-created_at&page_size=100') });
    const orders = (ordersQuery.data ? unwrap(ordersQuery.data) : []).filter((order) => (!search || `${order.order_number} ${order.customer_first_name} ${order.customer_last_name} ${order.customer_email}`.toLowerCase().includes(search.toLowerCase())) &&
        (!status || order.status === status));
    const update = useMutation({
        mutationFn: ({ orderNumber, value }: {
            orderNumber: string;
            value: Order['status'];
        }) => api.updateOrder(orderNumber, value),
        onSuccess: (order) => {
            queryClient.invalidateQueries({ queryKey: ['admin-orders'] });
            setSelected(order);
            toast.success(`Order ${order.order_number} updated`);
        },
        onError: () => toast.error('That status transition is not allowed'),
    });
    if (ordersQuery.isError)
        return <AdminErrorState resource="orders" />;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><p className={tw("admin-breadcrumb")}>Workspace / Orders</p><h1>Order management</h1><p>Track order status and customer fulfillment.</p></div><button type="button" onClick={() => exportCsv('digital-ptt-orders.csv', orders)}><Download size={18}/>Export</button></div>
      <section className={tw("admin-stats order-stats")}>
        <Metric label="Total orders" value={String(orders.length)} icon={ShoppingCart}/>
        <Metric label="Pending" value={String(orders.filter((order) => order.status === 'pending').length)} icon={Package}/>
        <Metric label="Completed" value={String(orders.filter((order) => order.status === 'completed').length)} icon={Boxes}/>
        <Metric label="Cancelled" value={String(orders.filter((order) => order.status === 'cancelled').length)} icon={X}/>
      </section>
      <section className={tw("admin-panel admin-section-gap")}>
        <div className={tw("orders-toolbar")}><h2>Recent orders</h2><div><Search size={18}/><input placeholder="Search order or customer" value={search} onChange={(event) => setSearch(event.target.value)}/></div><AdminSelect aria-label="Filter by order status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All status</option><option value="pending">Pending</option><option value="processing">Processing</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></AdminSelect></div>
        <OrderRows orders={orders} onSelect={setSelected}/>
      </section>
      {selected ? (<div className={tw("editor-backdrop")} role="presentation" onMouseDown={() => setSelected(null)}>
          <aside className={tw("order-editor")} onMouseDown={(event) => event.stopPropagation()}>
            <div className={tw("panel-heading")}><div><p className={tw("eyebrow")}>ORDER DETAILS</p><h2>{selected.order_number}</h2></div><button type="button" aria-label="Close order details" onClick={() => setSelected(null)}><X /></button></div>
            <p>{selected.customer_first_name} {selected.customer_last_name}<br />{selected.customer_email}<br />{selected.shipping_address}, {selected.shipping_city}</p>
            <div className={tw("order-editor-items")}>{selected.items.map((item) => <div key={item.id}><span>{item.product_name} x {item.quantity}</span><strong>${Number(item.line_total).toFixed(2)}</strong></div>)}</div>
            <div className={tw("order-editor-total")}><span>Total</span><strong>${Number(selected.total).toFixed(2)}</strong></div>
            <label>Order status<AdminSelect value={selected.status} onChange={(event) => update.mutate({ orderNumber: selected.order_number, value: event.target.value as Order['status'] })}><option value="pending">Pending</option><option value="processing">Processing</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></AdminSelect></label>
          </aside>
        </div>) : null}
    </main>);
}
