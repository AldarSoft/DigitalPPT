import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { ChevronRight, Download, Image as ImageIcon, Plus, Search, Star, Trash2, Upload, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, mediaUrl, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { Category, Product } from '../../../types'
import { AdminSelect } from '../components/AdminSelect'
import { AdminErrorState } from '../components/AdminErrorState'
import { Pagination } from '../../../components/Pagination'
import { exportAdminReport } from '../utils/exportAdminReport'
import { orderedProductImages, primaryProductImage } from '../../../lib/product-images'

const PAGE_SIZE = 20

export function AdminProductsPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [category, setCategory] = useState('');
    const [status, setStatus] = useState('');
    const [page, setPage] = useState(1);
    const [editing, setEditing] = useState<Product | 'new' | null>(null);
    const productsQuery = useQuery({
      queryKey: ['admin-products', search, category, status, page],
      queryFn: () => {
        const query = new URLSearchParams();
        if (search) query.set('search', search);
        if (category) query.set('category', category);
        if (status) query.set('status', status);
        query.set('ordering', '-updated_at');
        query.set('page', String(page));
        query.set('page_size', String(PAGE_SIZE));
        return api.products(query.toString());
      },
      placeholderData: keepPreviousData,
    });
    const products = productsQuery.data ? unwrap(productsQuery.data) : [];
    const totalProducts = productsQuery.data && !Array.isArray(productsQuery.data) ? productsQuery.data.count : products.length;
    const categoriesQuery = useQuery({ queryKey: ['categories'], queryFn: api.categories });
    const categories = categoriesQuery.data ? unwrap(categoriesQuery.data) : [];

    const remove = useMutation({
        mutationFn: (product: Product) => api.deleteProduct(product.slug),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-products'] }); toast.success('Product deleted'); },
        onError: () => toast.error('Could not delete product'),
    });
    if (productsQuery.isError || categoriesQuery.isError)
        return <AdminErrorState resource="products" />;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><h1>Products</h1><p>Manage catalog, pricing and inventory across {totalProducts} products.</p></div><button className={tw("admin-primary")} type="button" onClick={() => setEditing('new')}><Plus size={19}/>Add product</button></div>
      <section className={tw("admin-toolbar")}>
        <div><Search size={19}/><input placeholder="Search by name or SKU" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }}/></div>
        <AdminSelect aria-label="Filter by category" value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }}><option value="">All categories</option>{categories.map((item) => <option value={item.slug} key={item.id}>{item.name}</option>)}</AdminSelect>
        <AdminSelect aria-label="Filter by product status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All status</option><option value="published">Published</option><option value="draft">Draft</option><option value="archived">Archived</option></AdminSelect>
        <button type="button" onClick={() => void exportAdminReport({ kind: 'products', rows: products })}><Download size={17}/>Export page</button>
      </section>
      <section className={tw("admin-panel admin-table-wrap")}>
        <table className={tw("admin-table")}>
          <thead><tr><th>Product</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th>Updated</th><th>Action</th></tr></thead>
          <tbody>{products.map((product) => (<tr key={product.id}>
              <td><div className={tw("product-cell")}><img src={mediaUrl(primaryProductImage(product)?.image_url)} alt=""/><span><strong>{product.name}</strong><small>{product.sku}</small></span></div></td>
              <td>{product.category.name}</td><td>${Number(product.current_price).toFixed(2)}</td><td>{product.inventory_quantity}</td>
              <td><span className={tw(`status status-${product.status === 'published' ? 'completed' : 'pending'}`)}>{product.status}</span></td>
              <td>{new Date(product.updated_at).toLocaleDateString()}</td>
              <td><div className={tw("table-actions")}><button type="button" aria-label={`Edit ${product.name}`} onClick={() => setEditing(product)}><ChevronRight size={18}/></button><button type="button" aria-label={`Delete ${product.name}`} onClick={() => { if (confirm(`Delete ${product.name}?`))
            remove.mutate(product); }}><Trash2 size={17}/></button></div></td>
            </tr>))}</tbody>
        </table>
      </section>
      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={totalProducts}
        loading={productsQuery.isFetching}
        className="mt-3"
        onPageChange={setPage}
      />
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
};

type EditableProductImage = {
    key: string;
    imageUrl: string;
    previewUrl: string;
    altText: string;
    isPrimary: boolean;
    file?: File;
};

function ProductEditor({ product, categories, onClose }: {
    product: Product | null;
    categories: Category[];
    onClose: () => void;
}) {
    const queryClient = useQueryClient();
    const objectUrls = useRef(new Set<string>());
    const [images, setImages] = useState<EditableProductImage[]>(() => {
        const source = orderedProductImages(product?.images ?? []);
        const hasPrimary = source.some((image) => image.is_primary);
        return source.map((image, index) => ({
            key: `existing-${image.id ?? index}`,
            imageUrl: image.image_url,
            previewUrl: mediaUrl(image.image_url),
            altText: image.alt_text,
            isPrimary: image.is_primary || (!hasPrimary && index === 0),
        }));
    });
    useEffect(() => () => {
        objectUrls.current.forEach((url) => URL.revokeObjectURL(url));
        objectUrls.current.clear();
    }, []);
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
        mutationFn: async (data: ProductForm) => {
            const uploadedImages = await Promise.all(images.map(async (image) => ({
                ...image,
                imageUrl: image.file
                    ? (await api.uploadProductImage(image.file)).image_url
                    : image.imageUrl,
            })));
            const payload = {
                ...data,
                cost_price: data.cost_price || null,
                sale_price: data.sale_price || null,
                images: uploadedImages.map((image, index) => ({
                    image_url: image.imageUrl,
                    alt_text: image.altText || data.name,
                    is_primary: image.isPrimary,
                    sort_order: index,
                })),
            };
            return product ? api.updateProduct(product.slug, payload) : api.createProduct(payload);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-products'] });
            queryClient.invalidateQueries({ queryKey: ['products'] });
            toast.success(product ? 'Product saved' : 'Product created');
            onClose();
        },
        onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not save product'),
    });
    const selectImages = (files: FileList | null) => {
        if (!files?.length)
            return;
        const selectedFiles = Array.from(files);
        const validFiles = selectedFiles.filter((file) =>
            ['image/webp', 'image/jpeg', 'image/png'].includes(file.type) &&
            file.size <= 5 * 1024 * 1024,
        );
        if (validFiles.length !== selectedFiles.length)
            toast.error('Some files were skipped. Use WEBP, JPG, or PNG images up to 5 MB each.');
        if (!validFiles.length)
            return;
        setImages((current) => [
            ...current,
            ...validFiles.map((file, index) => {
                const previewUrl = URL.createObjectURL(file);
                objectUrls.current.add(previewUrl);
                return {
                    key: `new-${crypto.randomUUID()}`,
                    imageUrl: '',
                    previewUrl,
                    altText: '',
                    isPrimary: current.length === 0 && index === 0,
                    file,
                };
            }),
        ]);
    };
    const setPrimaryImage = (key: string) => {
        setImages((current) => current.map((image) => ({ ...image, isPrimary: image.key === key })));
    };
    const removeImage = (key: string) => {
        setImages((current) => {
            const removed = current.find((image) => image.key === key);
            if (removed?.previewUrl.startsWith('blob:')) {
                URL.revokeObjectURL(removed.previewUrl);
                objectUrls.current.delete(removed.previewUrl);
            }
            const remaining = current.filter((image) => image.key !== key);
            if (removed?.isPrimary && remaining.length)
                return remaining.map((image, index) => ({ ...image, isPrimary: index === 0 }));
            return remaining;
        });
    };
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
          <fieldset className={tw('product-image-upload')}>
            <legend>Product images</legend>
            {images.length ? <div className={tw('product-image-list')}>
              {images.map((image, index) => <article className={tw(`product-image-tile ${image.isPrimary ? 'primary' : ''}`)} key={image.key}>
                <span className={tw('product-image-preview')}>
                  <img src={image.previewUrl} alt={image.altText || `Product image ${index + 1}`} />
                </span>
                <div>
                  <strong>{image.isPrimary ? 'Storefront image' : `Gallery image ${index + 1}`}</strong>
                  <div className={tw('product-image-controls')}>
                    {image.isPrimary ? null : <button type="button" title="Use on product cards" aria-label={`Set image ${index + 1} as primary`} onClick={() => setPrimaryImage(image.key)}><Star size={16}/><span>Set primary</span></button>}
                    <button className={tw('danger')} type="button" title="Remove image" aria-label={`Remove image ${index + 1}`} onClick={() => removeImage(image.key)}><Trash2 size={16}/><span>Remove</span></button>
                  </div>
                </div>
              </article>)}
            </div> : <div className={tw('product-image-empty')}><ImageIcon size={25}/><span>No product images yet</span></div>}
            <label className={tw('image-upload-button')}>
              <Upload size={17} />
              <span>Add images</span>
              <input className="sr-only" type="file" multiple accept="image/png,image/jpeg,image/webp" onChange={(event) => { selectImages(event.target.files); event.currentTarget.value = ''; }} />
            </label>
            <small>The primary image appears on product cards. All images appear in the product gallery. WEBP, JPG, or PNG, up to 5 MB each.</small>
          </fieldset>
          <div className={tw("editor-row")}><label>Status<AdminSelect {...register('status')}><option value="draft">Draft</option><option value="published">Published</option><option value="archived">Archived</option></AdminSelect></label><label className={tw("editor-check")}><input type="checkbox" {...register('is_active')}/>Active in storefront</label></div>
          <div className={tw("editor-actions")}><button type="button" onClick={onClose}>Cancel</button><button className={tw("admin-primary")} type="submit" disabled={save.isPending}>{save.isPending ? 'Saving...' : 'Save product'}</button></div>
        </form>
      </aside>
    </div>);
}
