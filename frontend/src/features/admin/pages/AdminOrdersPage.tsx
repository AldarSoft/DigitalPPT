import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Boxes, Download, Package, Plus, Search, ShoppingCart, X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api, ApiError, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import { orderStatusKey, orderStatusLabel } from '../../../lib/status-labels'
import type { Order } from '../../../types'
import { AdminSelect } from '../components/AdminSelect'
import { AdminErrorState } from '../components/AdminErrorState'
import { Metric } from '../components/Metric'
import { OrderRows } from '../components/OrderRows'
import { Pagination } from '../../../components/Pagination'
import { ProductThumbnail } from '../../../components/ProductThumbnail'
import { StatusTimeline } from '../../../components/StatusTimeline'
import { exportAdminReport } from '../utils/exportAdminReport'
import { AdminManualOrderDialog } from '../components/AdminManualOrderDialog'

const PAGE_SIZE = 10
const ORDER_STEPS = [
    { value: 'pending', label: 'Pending' },
    { value: 'processing', label: 'Processing' },
    { value: 'completed', label: 'Completed' },
] as const

const ORDER_TRANSITIONS: Record<Order['status'], Order['status'][]> = {
    draft: ['pending', 'cancelled'],
    pending: ['backordered', 'processing', 'completed', 'cancelled'],
    backordered: ['scheduled', 'cancelled'],
    scheduled: ['processing', 'completed', 'cancelled'],
    processing: ['completed', 'cancelled'],
    completed: [],
    cancelled: [],
}

function orderUpdateError(error: Error) {
    if (!(error instanceof ApiError) || typeof error.data !== 'object' || !error.data) return 'Could not update the order status'
    const data = error.data as Record<string, unknown>
    if (data.inventory && typeof data.inventory === 'object') {
        const message = Object.values(data.inventory as Record<string, string>)[0]
        return `Awaiting stock. ${message}`
    }
    return typeof data.status === 'string' ? data.status : error.message
}

function availableTransitions(order: Order) {
    const shortage = order.items.some((item) => item.backordered_quantity > 0)
    return ORDER_TRANSITIONS[order.status].filter((status) => (
        (!shortage || !['processing', 'completed'].includes(status))
        && (!order.is_paid || status !== 'cancelled')
        && orderStatusKey(status) !== orderStatusKey(order.status)
    ))
}

export function AdminOrdersPage() {
    const queryClient = useQueryClient();
    const [searchParams, setSearchParams] = useSearchParams();
    const [search, setSearch] = useState('');
    const [status, setStatus] = useState(() => searchParams.get('status') ?? '');
    const [page, setPage] = useState(1);
    const [selected, setSelected] = useState<Order | null>(null);
    const [confirmingCancel, setConfirmingCancel] = useState(false);
    const [creating, setCreating] = useState(false);
    const ordersQuery = useQuery({
      queryKey: ['admin-orders', search, status, page],
      queryFn: () => {
        const query = new URLSearchParams();
        if (search) query.set('search', search);
        if (status) query.set('display_status', status);
        query.set('ordering', '-created_at');
        query.set('page', String(page));
        query.set('page_size', String(PAGE_SIZE));
        return api.orders(query.toString());
      },
      placeholderData: keepPreviousData,
    });
    const orders = ordersQuery.data ? unwrap(ordersQuery.data) : [];
    const orderTotal = ordersQuery.data && !Array.isArray(ordersQuery.data) ? ordersQuery.data.count : orders.length;
    const changeStatusFilter = (value: string) => {
        setStatus(value);
        setPage(1);
        setSearchParams((current) => {
            const next = new URLSearchParams(current);
            if (value) next.set('status', value);
            else next.delete('status');
            return next;
        }, { replace: true });
    };

    const update = useMutation({
        mutationFn: ({ orderNumber, value }: {
            orderNumber: string;
            value: Order['status'];
        }) => api.updateOrder(orderNumber, value),
        onSuccess: (order) => {
            queryClient.invalidateQueries({ queryKey: ['admin-orders'] });
            setSelected((current) => current ? { ...current, status: order.status, updated_at: order.updated_at } : null);
            setConfirmingCancel(false);
            toast.success('Order status updated');
        },
        onError: (error) => toast.error(orderUpdateError(error)),
    });
    if (ordersQuery.isError)
        return <AdminErrorState resource="orders" />;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><p className={tw("admin-breadcrumb")}>Workspace / Orders</p><h1>Order management</h1><p>Track order status and customer fulfillment.</p></div><div className={tw('page-actions')}><button className={tw("admin-link-button admin-primary")} type="button" onClick={() => setCreating(true)}><Plus size={18}/>Create order</button><button className={tw("admin-link-button")} type="button" onClick={() => void exportAdminReport({ kind: 'orders', rows: orders })}><Download size={18}/>Export page</button></div></div>
      <section className={tw("admin-stats order-stats")}>
        <Metric label="Total orders" value={String(orderTotal)} icon={ShoppingCart}/>
        <Metric label="Pending on page" value={String(orders.filter((order) => orderStatusKey(order.status) === 'pending').length)} icon={Package}/>
        <Metric label="Completed on page" value={String(orders.filter((order) => orderStatusKey(order.status) === 'completed').length)} icon={Boxes}/>
        <Metric label="Cancelled on page" value={String(orders.filter((order) => orderStatusKey(order.status) === 'cancelled').length)} icon={X}/>
      </section>
      <section className={tw("admin-panel admin-section-gap")}>
        <div className={tw("orders-toolbar")}><h2>Recent orders</h2><div><Search size={18}/><input placeholder="Search order or customer" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }}/></div><AdminSelect aria-label="Filter by order status" value={status} onChange={(event) => changeStatusFilter(event.target.value)}><option value="">All status</option><option value="draft">Draft</option><option value="pending">Awaiting payment</option><option value="backordered">Awaiting stock</option><option value="processing">Processing</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></AdminSelect></div>
        <OrderRows orders={orders} onSelect={(order) => { setConfirmingCancel(false); setSelected(order); }}/>
      </section>
      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={orderTotal}
        loading={ordersQuery.isFetching}
        className="mt-3"
        onPageChange={setPage}
      />
      {creating ? <AdminManualOrderDialog onClose={() => setCreating(false)} onCreated={(order) => { setCreating(false); queryClient.invalidateQueries({ queryKey: ['admin-orders'] }); setSelected(order) }} /> : null}
      {selected ? (<div className={tw("editor-backdrop")} role="presentation" onMouseDown={() => { setConfirmingCancel(false); setSelected(null); }}>
          <aside className={tw("order-editor")} role="dialog" aria-modal="true" aria-labelledby="admin-order-details-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className={tw("panel-heading")}><div><p className={tw("eyebrow")}>ORDER DETAILS</p><h2 id="admin-order-details-title">{selected.order_number}</h2></div><button type="button" aria-label="Close order details" onClick={() => { setConfirmingCancel(false); setSelected(null); }}><X /></button></div>
            <p>{selected.customer_first_name} {selected.customer_last_name}<br />{selected.customer_email}<br />{selected.shipping_address}, {selected.shipping_city}</p>
            {selected.quote_number ? <p className="mt-3 text-sm text-text-soft">Linked quote: <Link className={tw('view-order')} to={`/admin/quotes?quote=${encodeURIComponent(selected.quote_number)}`}>{selected.quote_number}</Link></p> : null}
            <div className={tw("order-editor-items")}>{selected.items.map((item) => <div key={item.id}><div className={tw('record-item-main')}><ProductThumbnail imageUrl={item.image_url} name={item.product_name} /><span>{item.product_name}<small>{item.sku || 'Product'} · Qty {item.quantity}</small>{item.fulfillment_status !== 'not_required' ? <small className={item.backordered_quantity ? 'text-warning' : 'text-success'}>{item.backordered_quantity ? `${item.reserved_quantity} reserved · ${item.backordered_quantity} awaiting stock` : `${item.reserved_quantity} ready to ship`}</small> : null}</span></div><strong>${Number(item.line_total).toFixed(2)}</strong></div>)}</div>
            <div className={tw("order-editor-total")}><span>Total</span><strong>${Number(selected.total).toFixed(2)}</strong></div>
            {selected.status === 'backordered' ? <div className="mt-4 rounded-control border border-warning bg-warning-soft p-3 text-sm text-warning"><strong>Awaiting inventory</strong><p className="mt-1 text-xs">Payment is confirmed. Available units are reserved, and the remaining units will be allocated automatically when inventory increases.</p></div> : null}
            {selected.status === 'draft' ? <div className="mt-4 rounded-control border border-border bg-surface-muted p-3 text-sm text-muted"><strong className="block text-ink">Admin Draft</strong><p className="mt-1">This order is hidden from the client and has no payment or provisioning activity.</p></div> : <StatusTimeline noun="Order" currentStatus={orderStatusKey(selected.status)} initialStatus="pending" createdAt={selected.created_at} updatedAt={selected.updated_at} steps={ORDER_STEPS} />}
            {availableTransitions(selected).length ? <label>Order status<AdminSelect value={selected.status} onChange={(event) => { const value = event.target.value as Order['status']; if (value === 'cancelled') setConfirmingCancel(true); else update.mutate({ orderNumber: selected.order_number, value }); }}><option value={selected.status}>{orderStatusLabel(selected.status)}</option>{availableTransitions(selected).map((value) => <option value={value} key={value}>{orderStatusLabel(value)}</option>)}</AdminSelect></label> : <p className="mt-4 text-sm text-text-soft">This order is {orderStatusLabel(selected.status)} and cannot be changed.</p>}
            {confirmingCancel ? <div className={tw('quote-close-alert')} role="alertdialog" aria-labelledby="cancel-order-title" aria-describedby="cancel-order-description"><AlertTriangle size={20} /><div><strong id="cancel-order-title">Cancel this order?</strong><p id="cancel-order-description">This action is permanent. Any inventory already deducted for this order will be restored.</p></div><div><button type="button" onClick={() => setConfirmingCancel(false)}>Keep order</button><button type="button" disabled={update.isPending} onClick={() => update.mutate({ orderNumber: selected.order_number, value: 'cancelled' })}>{update.isPending ? 'Cancelling...' : 'Cancel order'}</button></div></div> : null}
          </aside>
        </div>) : null}
    </main>);
}
