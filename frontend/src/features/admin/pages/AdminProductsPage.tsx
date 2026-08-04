import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { ChevronRight, Download, Plus, Search, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, mediaUrl, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { Category, Product } from '../../../types'
import { AdminSelect } from '../components/AdminSelect'
import { AdminErrorState } from '../components/AdminErrorState'
import { exportCsv } from '../utils/exportCsv'

export function AdminProductsPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [category, setCategory] = useState('');
    const [status, setStatus] = useState('');
    const [editing, setEditing] = useState<Product | 'new' | null>(null);
    const productsQuery = useQuery({ queryKey: ['admin-products'], queryFn: () => api.products('ordering=-updated_at&page_size=100') });
    const categoriesQuery = useQuery({ queryKey: ['categories'], queryFn: api.categories });
    const products = (productsQuery.data ? unwrap(productsQuery.data) : []).filter((product) => (!search || `${product.name} ${product.sku}`.toLowerCase().includes(search.toLowerCase())) &&
        (!category || product.category.slug === category) &&
        (!status || product.status === status));
    const categories = categoriesQuery.data ? unwrap(categoriesQuery.data) : [];
    const remove = useMutation({
        mutationFn: (product: Product) => api.deleteProduct(product.slug),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-products'] }); toast.success('Product deleted'); },
        onError: () => toast.error('Could not delete product'),
    });
    if (productsQuery.isError || categoriesQuery.isError)
        return <AdminErrorState resource="products" />;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><h1>Products</h1><p>Manage catalog, pricing and inventory across {products.length} products.</p></div><button className={tw("admin-primary")} type="button" onClick={() => setEditing('new')}><Plus size={19}/>Add product</button></div>
      <section className={tw("admin-toolbar")}>
        <div><Search size={19}/><input placeholder="Search by name or SKU" value={search} onChange={(event) => setSearch(event.target.value)}/></div>
        <AdminSelect aria-label="Filter by category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((item) => <option value={item.slug} key={item.id}>{item.name}</option>)}</AdminSelect>
        <AdminSelect aria-label="Filter by product status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All status</option><option value="published">Published</option><option value="draft">Draft</option><option value="archived">Archived</option></AdminSelect>
        <button type="button" onClick={() => exportCsv('digital-ptt-products.csv', products)}><Download size={17}/>Export</button>
      </section>
      <section className={tw("admin-panel admin-table-wrap")}>
        <table className={tw("admin-table")}>
          <thead><tr><th>Product</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th>Updated</th><th>Action</th></tr></thead>
          <tbody>{products.map((product) => (<tr key={product.id}>
              <td><div className={tw("product-cell")}><img src={mediaUrl(product.images[0]?.image_url)} alt=""/><span><strong>{product.name}</strong><small>{product.sku}</small></span></div></td>
              <td>{product.category.name}</td><td>${Number(product.current_price).toFixed(2)}</td><td>{product.inventory_quantity}</td>
              <td><span className={tw(`status status-${product.status === 'published' ? 'completed' : 'pending'}`)}>{product.status}</span></td>
              <td>{new Date(product.updated_at).toLocaleDateString()}</td>
              <td><div className={tw("table-actions")}><button type="button" aria-label={`Edit ${product.name}`} onClick={() => setEditing(product)}><ChevronRight size={18}/></button><button type="button" aria-label={`Delete ${product.name}`} onClick={() => { if (confirm(`Delete ${product.name}?`))
            remove.mutate(product); }}><Trash2 size={17}/></button></div></td>
            </tr>))}</tbody>
        </table>
      </section>
      {editing ? <ProductEditor product={editing === 'new' ? null : editing} categories={categories} onClose={() => setEditing(null)}/> : null}
    </main>);
}
type ProductForm = {
    category: number;
    name: string;
    sku: string;
    brand: string;
    short_description: string;
    description: string;
    price: string;
    cost_price: string;
    sale_price: string;
    inventory_quantity: number;
    status: Product['status'];
    is_featured: boolean;
    is_active: boolean;
    image_url: string;
};
function ProductEditor({ product, categories, onClose }: {
    product: Product | null;
    categories: Category[];
    onClose: () => void;
}) {
    const queryClient = useQueryClient();
    const { register, handleSubmit } = useForm<ProductForm>({
        defaultValues: product ? {
            category: product.category.id,
            name: product.name,
            sku: product.sku,
            brand: product.brand,
            short_description: product.short_description,
            description: product.description,
            price: product.price,
            cost_price: product.cost_price ?? '',
            sale_price: product.sale_price ?? '',
            inventory_quantity: product.inventory_quantity,
            status: product.status,
            is_featured: product.is_featured,
            is_active: product.is_active,
            image_url: product.images[0]?.image_url ?? '',
        } : {
            category: categories[0]?.id,
            brand: 'Digital PTT',
            status: 'draft',
            is_active: true,
            is_featured: false,
            inventory_quantity: 0,
        },
    });
    const save = useMutation({
        mutationFn: (values: ProductForm) => {
            const { image_url, ...data } = values;
            const payload = {
                ...data,
                cost_price: data.cost_price || null,
                sale_price: data.sale_price || null,
                images: image_url ? [{ image_url, alt_text: data.name, is_primary: true, sort_order: 0 }] : [],
            };
            return product ? api.updateProduct(product.slug, payload) : api.createProduct(payload);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-products'] });
            queryClient.invalidateQueries({ queryKey: ['products'] });
            toast.success(product ? 'Product saved' : 'Product created');
            onClose();
        },
        onError: () => toast.error('Could not save product'),
    });
    return (<div className={tw("editor-backdrop")} role="presentation" onMouseDown={onClose}>
      <aside className={tw("product-editor")} role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div><h2>{product ? 'Edit product' : 'Add product'}</h2><button type="button" aria-label="Close editor" onClick={onClose}><X /></button></div>
        <form onSubmit={handleSubmit((values) => save.mutate(values))}>
          <label>Product name<input required {...register('name')}/></label>
          <div className={tw("editor-row")}><label>SKU<input required {...register('sku')}/></label><label>Brand<input {...register('brand')}/></label></div>
          <label>Category<AdminSelect {...register('category', { valueAsNumber: true })}>{categories.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</AdminSelect></label>
          <div className={tw("editor-row")}><label>Price<input type="number" min="0" step="0.01" required {...register('price')}/></label><label>Sale price<input type="number" min="0" step="0.01" {...register('sale_price')}/></label></div>
          <div className={tw("editor-row")}><label>Cost price<input type="number" min="0" step="0.01" {...register('cost_price')}/></label><label>Stock quantity<input type="number" min="0" {...register('inventory_quantity', { valueAsNumber: true })}/></label></div>
          <label>Short description<input {...register('short_description')}/></label>
          <label>Description<textarea rows={4} {...register('description')}/></label>
          <label>Image URL<input placeholder="/media/products/example.jpg" {...register('image_url')}/></label>
          <div className={tw("editor-row")}><label>Status<AdminSelect {...register('status')}><option value="draft">Draft</option><option value="published">Published</option><option value="archived">Archived</option></AdminSelect></label><label className={tw("editor-check")}><input type="checkbox" {...register('is_active')}/>Active in storefront</label></div>
          <div className={tw("editor-actions")}><button type="button" onClick={onClose}>Cancel</button><button className={tw("admin-primary")} type="submit" disabled={save.isPending}>{save.isPending ? 'Saving...' : 'Save product'}</button></div>
        </form>
      </aside>
    </div>);
}
