import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Boxes, Download, Package, Plus, Search, Warehouse, X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { toast } from 'sonner'
import { api, mediaUrl, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { Product } from '../../../types'
import { AdminSelect } from '../components/AdminSelect'
import { AdminErrorState } from '../components/AdminErrorState'
import { Metric } from '../components/Metric'
import { exportAdminReport } from '../utils/exportAdminReport'
import { primaryProductImage } from '../../../lib/product-images'

export function AdminInventoryPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [stockFilter, setStockFilter] = useState('');
    const [editing, setEditing] = useState<Product | null>(null);
    const [mode, setMode] = useState<'add' | 'set'>('add');
    const [quantity, setQuantity] = useState(1);
    const [reason, setReason] = useState('stock_received');
    const productsQuery = useQuery({ queryKey: ['admin-products'], queryFn: () => api.products('ordering=inventory_quantity&page_size=100') });
    const allProducts = productsQuery.data ? unwrap(productsQuery.data) : [];
    const stockTrackedProducts = allProducts.filter((product) => product.is_stock_tracked !== false);
    const products = allProducts.filter((product) => (!search || `${product.name} ${product.sku}`.toLowerCase().includes(search.toLowerCase())) &&
        (!stockFilter || (product.is_stock_tracked !== false && (stockFilter === 'out' ? product.inventory_quantity === 0 : stockFilter === 'low' ? product.inventory_quantity > 0 && product.inventory_quantity <= 5 : product.inventory_quantity > 5))));
    const save = useMutation({
        mutationFn: (product: Product) => api.adjustInventory(product.slug, { mode, quantity, reason }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-products'] });
            toast.success('Inventory updated');
            setEditing(null);
        },
        onError: () => toast.error('Could not update inventory'),
    });
    if (productsQuery.isError)
        return <AdminErrorState resource="inventory" />;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><p className={tw("admin-breadcrumb")}>Workspace / Inventory</p><h1>Inventory management</h1><p>Monitor stock levels and reorder needs.</p></div><NavLink className={tw("admin-link-button admin-primary")} to="/admin/products"><Plus size={18}/>Add stock item</NavLink></div>
      <section className={tw("admin-stats")}>
        <Metric label="Total SKUs" value={String(allProducts.length)} icon={Boxes}/>
        <Metric label="In stock" value={String(stockTrackedProducts.filter((product) => product.inventory_quantity > 5).length)} icon={Warehouse}/>
        <Metric label="Low stock" value={String(stockTrackedProducts.filter((product) => product.inventory_quantity > 0 && product.inventory_quantity <= 5).length)} icon={Package}/>
        <Metric label="Out of stock" value={String(stockTrackedProducts.filter((product) => product.inventory_quantity === 0).length)} icon={X}/>
      </section>
      <section className={tw("admin-toolbar compact-toolbar")}><div><Search size={19}/><input placeholder="Search product or SKU" value={search} onChange={(event) => setSearch(event.target.value)}/></div><AdminSelect aria-label="Filter by stock level" value={stockFilter} onChange={(event) => setStockFilter(event.target.value)}><option value="">All stock levels</option><option value="healthy">In stock</option><option value="low">Low stock</option><option value="out">Out of stock</option></AdminSelect><button type="button" onClick={() => void exportAdminReport({ kind: 'inventory', rows: products })}><Download size={17}/>Export</button></section>
      <section className={tw("admin-panel admin-table-wrap")}>
        <table className={tw("admin-table")}><thead><tr><th>Product</th><th>SKU</th><th>On hand</th><th>Reserved</th><th>Available</th><th>Awaiting stock</th><th>Updated</th><th>Action</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}>
          <td><div className={tw("product-cell")}><img src={mediaUrl(primaryProductImage(product)?.image_url)} alt=""/><strong>{product.name}</strong></div></td><td>{product.sku}</td><td><strong>{product.is_stock_tracked === false ? '—' : product.on_hand_inventory_quantity ?? product.inventory_quantity}</strong></td><td>{product.is_stock_tracked === false ? '—' : product.reserved_inventory_quantity ?? 0}</td><td>{product.is_stock_tracked === false ? <span className={tw("status status-completed")}>Always available</span> : <div className={tw('inventory-available')}><strong>{product.inventory_quantity}</strong><span className={tw(`status status-${product.inventory_quantity === 0 ? 'cancelled' : product.inventory_quantity <= 5 ? 'pending' : 'completed'}`)}>{product.inventory_quantity === 0 ? 'out of stock' : product.inventory_quantity <= 5 ? 'low stock' : 'in stock'}</span></div>}</td><td>{product.is_stock_tracked === false || !(product.backordered_inventory_quantity ?? 0) ? (product.is_stock_tracked === false ? '—' : '0') : <span className={tw('status status-pending')}>{product.backordered_inventory_quantity}</span>}</td><td>{product.updated_at ? new Date(product.updated_at).toLocaleDateString() : '—'}</td><td>{product.is_stock_tracked === false ? <span className="text-xs text-muted">Not stock tracked</span> : <button className={tw("table-action")} type="button" onClick={() => { setEditing(product); setMode('add'); setQuantity(1); setReason('stock_received'); }}>Adjust stock</button>}</td>
        </tr>)}</tbody></table>
      </section>
      {editing ? (() => {
        const onHand = editing.on_hand_inventory_quantity ?? editing.inventory_quantity
        const reserved = editing.reserved_inventory_quantity ?? 0
        const backordered = editing.backordered_inventory_quantity ?? 0
        const quantityAfter = mode === 'add' ? onHand + quantity : quantity
        const allocatedToBackorders = mode === 'add' ? Math.min(backordered, Math.max(0, quantityAfter - reserved)) : 0
        const availableAfter = Math.max(0, quantityAfter - reserved - allocatedToBackorders)
        const invalidCount = mode === 'set' && quantity < reserved
        return <div className={tw("editor-backdrop")} role="presentation" onMouseDown={() => setEditing(null)}><aside className={tw("stock-editor")} role="dialog" aria-modal="true" aria-labelledby="inventory-adjust-title" onMouseDown={(event) => event.stopPropagation()}><div className={tw("panel-heading")}><div><p className={tw("eyebrow")}>INVENTORY ADJUSTMENT</p><h2 id="inventory-adjust-title">{editing.name}</h2></div><button type="button" aria-label="Close inventory editor" onClick={() => setEditing(null)}><X /></button></div><dl className={tw('inventory-adjustment-summary')}><div><dt>On hand</dt><dd>{onHand}</dd></div><div><dt>Reserved for paid orders</dt><dd>{reserved}</dd></div><div><dt>Available to sell</dt><dd>{editing.inventory_quantity}</dd></div>{backordered ? <div><dt>Awaiting stock</dt><dd>{backordered}</dd></div> : null}</dl><div className={tw('inventory-mode-control')} role="group" aria-label="Adjustment mode"><button type="button" className={mode === 'add' ? 'is-active' : ''} onClick={() => { setMode('add'); setQuantity(1) }}>Add stock</button><button type="button" className={mode === 'set' ? 'is-active' : ''} onClick={() => { setMode('set'); setQuantity(onHand) }}>Set counted quantity</button></div><label>{mode === 'add' ? 'Units received' : 'Counted quantity on hand'}<input type="number" min={mode === 'add' ? 1 : reserved} value={quantity} onChange={(event) => setQuantity(Math.max(0, Number(event.target.value)))} /></label><label>Reason<select value={reason} onChange={(event) => setReason(event.target.value)}><option value="stock_received">Stock received</option><option value="warehouse_count">Warehouse count</option><option value="damaged_correction">Damaged or correction</option><option value="other">Other</option></select></label>{invalidCount ? <p className={tw('inventory-adjustment-error')}>Counted stock cannot be lower than {reserved}, because those units are reserved for paid orders.</p> : null}{mode === 'add' && allocatedToBackorders ? <p className={tw('inventory-adjustment-impact')}>{allocatedToBackorders} incoming {allocatedToBackorders === 1 ? 'unit' : 'units'} will be reserved for awaiting paid orders. Available to sell after saving: {availableAfter}.</p> : null}<div className={tw("editor-actions")}><button type="button" onClick={() => setEditing(null)}>Cancel</button><button className={tw("admin-primary")} type="button" onClick={() => save.mutate(editing)} disabled={save.isPending || invalidCount || (mode === 'add' && quantity < 1)}>{save.isPending ? 'Saving...' : mode === 'add' ? 'Add to inventory' : 'Save counted quantity'}</button></div></aside></div>
      })() : null}
    </main>);
}
