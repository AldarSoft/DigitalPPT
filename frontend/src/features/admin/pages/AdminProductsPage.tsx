import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { ArrowDown, ArrowUp, ChevronRight, Download, FolderTree, Image as ImageIcon, Pencil, Plus, Search, Star, Trash2, Upload, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, mediaUrl, unwrap, type CategoryInput } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { Category, Product, ProductLayout, ProductPresentation } from '../../../types'
import { ProductPresentationEditor } from '../components/ProductPresentationEditor'
import { invalidateCatalog } from '../../../lib/invalidate-catalog'
import { Link } from 'react-router-dom'
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
    const [categoryManagerOpen, setCategoryManagerOpen] = useState(false);
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
        return api.adminProducts(query.toString());
      },
      placeholderData: keepPreviousData,
    });
    const products = productsQuery.data ? unwrap(productsQuery.data) : [];
    const totalProducts = productsQuery.data && !Array.isArray(productsQuery.data) ? productsQuery.data.count : products.length;
    const categoriesQuery = useQuery({
      queryKey: ['admin-categories'],
      queryFn: api.adminCategories,
    });
    const categories = categoriesQuery.data ? unwrap(categoriesQuery.data) : [];
    const licenseProductsQuery = useQuery({
      queryKey: ['admin-license-products'],
      queryFn: () => api.adminProducts('licensing_role=license_product&page_size=100'),
    });
    const licenseProducts = licenseProductsQuery.data ? unwrap(licenseProductsQuery.data) : [];

    const remove = useMutation({
        mutationFn: (product: Product) => api.deleteProduct(product.slug),
        onSuccess: () => { invalidateCatalog(queryClient); toast.success('Product deleted'); },
        onError: () => toast.error('Could not delete product'),
    });
    if (productsQuery.isError || categoriesQuery.isError || licenseProductsQuery.isError)
        return <AdminErrorState resource="products" />;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><h1>Products</h1><p>Manage catalog, pricing and inventory across {totalProducts} products.</p></div><button className={tw("admin-primary")} type="button" onClick={() => setEditing('new')}><Plus size={19}/>Add product</button></div>
      <section className={tw("admin-toolbar")}>
        <div><Search size={19}/><input placeholder="Search by name or SKU" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }}/></div>
        <AdminSelect aria-label="Filter by category" value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }}><option value="">All categories</option>{categories.map((item) => <option value={item.slug} key={item.id}>{item.name}</option>)}</AdminSelect>
        <AdminSelect aria-label="Filter by product status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All status</option><option value="published">Published</option><option value="draft">Draft</option><option value="archived">Archived</option></AdminSelect>
        <button type="button" onClick={() => setCategoryManagerOpen(true)}><FolderTree size={17}/>Manage categories</button>
        <button type="button" onClick={() => void exportAdminReport({ kind: 'products', rows: products })}><Download size={17}/>Export page</button>
      </section>
      <section className={tw("admin-panel admin-table-wrap")}>
        <table className={tw("admin-table")}>
          <thead><tr><th>Product</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th>Updated</th><th>Action</th></tr></thead>
          <tbody>{products.map((product) => (<tr key={product.id}>
              <td><div className={tw("product-cell")}><img src={mediaUrl(primaryProductImage(product)?.image_url)} alt=""/><span><strong>{product.name}</strong><small>{product.sku}</small></span></div></td>
              <td>{product.category.name}</td><td>${Number(product.current_price).toFixed(2)}</td><td>{product.inventory_quantity}</td>
              <td><span className={tw(`status status-${product.status === 'published' ? 'completed' : 'pending'}`)}>{product.status}</span></td>
              <td>{product.updated_at ? new Date(product.updated_at).toLocaleDateString() : '—'}</td>
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
      {editing ? <ProductEditor product={editing === 'new' ? null : editing} categories={categories} licenseProducts={licenseProducts} onClose={() => setEditing(null)}/> : null}
      {categoryManagerOpen ? <CategoryManager categories={categories} onClose={() => setCategoryManagerOpen(false)}/> : null}
    </main>);
}

function CategoryManager({ categories, onClose }: { categories: Category[]; onClose: () => void }) {
    const queryClient = useQueryClient();
    const [editing, setEditing] = useState<Category | 'new' | null>(null);
    const remove = useMutation({
        mutationFn: (item: Category) => api.deleteCategory(item.slug),
        onSuccess: () => {
            invalidateCatalog(queryClient);
            queryClient.invalidateQueries({ queryKey: ['admin-products'] });
            toast.success('Category deleted');
        },
        onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not delete category'),
    });
    const category = editing && editing !== 'new' ? editing : null;
    return (<div className={tw("editor-backdrop")} role="presentation" onMouseDown={onClose}>
      <aside className={tw("product-editor category-manager")} role="dialog" aria-modal="true" aria-label="Manage product categories" onMouseDown={(event) => event.stopPropagation()}>
        <div><span><h2>{editing ? (category ? 'Edit category' : 'Add category') : 'Categories'}</h2>{!editing ? <small>{categories.length} {categories.length === 1 ? 'category' : 'categories'}</small> : null}</span><button type="button" aria-label="Close category manager" onClick={onClose}><X /></button></div>
        {editing ? <CategoryEditor category={category} onCancel={() => setEditing(null)} onSaved={() => setEditing(null)}/> : <>
          <button className={tw("action-button action-button-primary mt-5 w-full")} type="button" onClick={() => setEditing('new')}><Plus size={17}/>Add category</button>
          <section className={tw("category-list")} aria-label="Product categories">
            <div className={tw("category-list-head")} aria-hidden="true"><span>Category</span><span>Products</span><span>Status</span><span>Actions</span></div>
            {categories.map((item) => <article className={tw("category-list-row")} key={item.id}>
              <span className={tw("min-w-0")}><strong>{item.name}</strong><small>{item.slug}</small></span>
              <span className={tw("category-product-count")}>{item.product_count} {item.product_count === 1 ? 'product' : 'products'}</span>
              <span className={tw(`category-status ${item.is_active ? 'active' : 'inactive'}`)}>{item.is_active ? 'Active' : 'Inactive'}</span>
              <span className={tw("table-actions justify-end")}>
                <button type="button" title="Edit category" aria-label={`Edit ${item.name}`} onClick={() => setEditing(item)}><Pencil size={16}/></button>
                <button className={tw("disabled:cursor-not-allowed disabled:opacity-40")} type="button" title={item.product_count ? 'Move products before deleting' : 'Delete category'} aria-label={`Delete ${item.name}`} disabled={item.product_count > 0 || remove.isPending} onClick={() => { if (confirm(`Delete ${item.name}?`)) remove.mutate(item); }}><Trash2 size={16}/></button>
              </span>
            </article>)}
            {!categories.length ? <div className={tw("admin-empty-row")}><FolderTree size={26}/><strong>No categories yet</strong><span>Add the first category to organize products.</span></div> : null}
          </section>
        </>}
      </aside>
    </div>);
}

function CategoryEditor({ category, onCancel, onSaved }: { category: Category | null; onCancel: () => void; onSaved: () => void }) {
    const queryClient = useQueryClient();
    const { register, handleSubmit } = useForm<CategoryInput>({
        defaultValues: category ? {
            name: category.name,
            slug: category.slug,
            description: category.description,
            image_url: category.image_url,
            is_active: category.is_active,
        } : {
            name: '',
            slug: '',
            description: '',
            image_url: '',
            is_active: true,
        },
    });
    const save = useMutation({
        mutationFn: (data: CategoryInput) => category
            ? api.updateCategory(category.slug, data)
            : api.createCategory(data),
        onSuccess: () => {
            invalidateCatalog(queryClient);
            queryClient.invalidateQueries({ queryKey: ['admin-products'] });
            queryClient.invalidateQueries({ queryKey: ['products'] });
            toast.success(category ? 'Category saved' : 'Category created');
            onSaved();
        },
        onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not save category'),
    });
    return (<form onSubmit={handleSubmit((values) => save.mutate(values))}>
      <label>Category name<input required {...register('name')}/></label>
      <label>Slug<input placeholder="Generated automatically when empty" {...register('slug')}/></label>
      <label>Description<textarea rows={4} {...register('description')}/></label>
      <label>Image URL<input {...register('image_url')}/></label>
      <label className={tw("editor-check")}><input type="checkbox" {...register('is_active')}/>Active in storefront</label>
      <div className={tw("editor-actions")}><button type="button" onClick={onCancel}>Cancel</button><button className={tw("admin-primary")} type="submit" disabled={save.isPending}>{save.isPending ? 'Saving...' : 'Save category'}</button></div>
    </form>);
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
    bulk_minimum_quantity: string;
    bulk_unit_price: string;
    inventory_quantity: number;
    licensing_role: Product['licensing_role'];
    required_license_product_id: number | null;
    license_capacity: string;
    license_term_days: string;
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

type EditableProductSpecification = {
    show_in_highlights: boolean;
    id: string;
    key: string;
    value: string;
};

function ProductEditor({ product, categories, licenseProducts, onClose }: {
    product: Product | null;
    categories: Category[];
    licenseProducts: Product[];
    onClose: () => void;
}) {
    const queryClient = useQueryClient();
    const defaultsQuery = useQuery({ queryKey: ['site-settings'], queryFn: api.siteSettings });
    const [layout, setLayout] = useState<ProductLayout>(product?.detail_layout ?? 'accessory');
    const [overrides, setOverrides] = useState<Partial<ProductPresentation>>(product?.presentation_overrides ?? {});
    const dialogRef = useRef<HTMLElement>(null);
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
    const [specifications, setSpecifications] = useState<EditableProductSpecification[]>(() =>
        (product?.specifications ?? []).map((specification) => ({
            id: crypto.randomUUID(),
            key: specification.key,
            value: specification.value,
            show_in_highlights: specification.show_in_highlights ?? false,
        })),
    );
    useEffect(() => () => {
        objectUrls.current.forEach((url) => URL.revokeObjectURL(url));
        objectUrls.current.clear();
    }, []);
    const { register, handleSubmit, control, formState: { isDirty } } = useForm<ProductForm>({
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
            bulk_minimum_quantity: product.bulk_minimum_quantity?.toString() ?? '',
            bulk_unit_price: product.bulk_unit_price ?? '',
            inventory_quantity: product.on_hand_inventory_quantity ?? product.inventory_quantity,
            licensing_role: product.licensing_role,
            required_license_product_id: product.required_license_product?.id ?? null,
            license_capacity: product.license_capacity?.toString() ?? '',
            license_term_days: product.license_term_days?.toString() ?? '',
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
            licensing_role: 'standard',
            required_license_product_id: null,
            license_capacity: '',
            license_term_days: '',
        },
    });
    const licensingRole = useWatch({ control, name: 'licensing_role' });
    const [initialExtras] = useState(() => JSON.stringify({ images, specifications, layout, overrides }));
    const dirty = isDirty || initialExtras !== JSON.stringify({ images, specifications, layout, overrides });
    const requestClose = () => { if (!dirty || window.confirm('Discard unsaved product changes?')) onClose(); };
    useEffect(() => {
        const element = dialogRef.current;
        const previous = document.activeElement as HTMLElement | null;
        element?.focus();
        const trap = (event: KeyboardEvent) => {
            if (event.key !== 'Tab') return;
            const focusable = Array.from(element?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary') ?? []).filter((item) => item.offsetParent !== null && !item.closest('fieldset:disabled'));
            const first = focusable[0], last = focusable[focusable.length - 1];
            if (event.shiftKey && (document.activeElement === first || document.activeElement === element)) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        };
        element?.addEventListener('keydown', trap);
        return () => { element?.removeEventListener('keydown', trap); previous?.focus(); };
    }, []);
    useEffect(() => {
        const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
        window.addEventListener('beforeunload', warn);
        return () => window.removeEventListener('beforeunload', warn);
    }, [dirty]);
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
                detail_layout: layout,
                presentation_overrides: overrides,
                cost_price: data.cost_price || null,
                sale_price: data.sale_price || null,
                bulk_minimum_quantity: data.bulk_minimum_quantity ? Number(data.bulk_minimum_quantity) : null,
                bulk_unit_price: data.bulk_unit_price || null,
                required_license_product_id: data.licensing_role === 'licensed_product'
                    ? data.required_license_product_id
                    : null,
                license_capacity: data.licensing_role === 'license_product'
                    ? Number(data.license_capacity)
                    : null,
                license_term_days: data.licensing_role === 'license_product'
                    ? Number(data.license_term_days)
                    : null,
                inventory_quantity: data.licensing_role === 'license_product'
                    ? 0
                    : data.inventory_quantity,
                images: uploadedImages.map((image, index) => ({
                    image_url: image.imageUrl,
                    alt_text: image.altText || data.name,
                    is_primary: image.isPrimary,
                    sort_order: index,
                })),
                specifications: specifications.map((specification, index) => ({
                    show_in_highlights: specification.show_in_highlights,
                    key: specification.key.trim(),
                    value: specification.value.trim(),
                    sort_order: index,
                })),
            };
            return product ? api.updateProduct(product.slug, payload) : api.createProduct(payload);
        },
        onSuccess: () => {
            invalidateCatalog(queryClient);
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
    const updateSpecification = (id: string, field: 'key' | 'value', value: string) => {
        setSpecifications((current) => current.map((specification) =>
            specification.id === id ? { ...specification, [field]: value } : specification,
        ));
    };
    const moveSpecification = (index: number, direction: -1 | 1) => {
        setSpecifications((current) => {
            const destination = index + direction;
            if (destination < 0 || destination >= current.length) return current;
            const next = [...current];
            [next[index], next[destination]] = [next[destination], next[index]];
            return next;
        });
    };
    return (<div className={`${tw("editor-backdrop")} !z-[120]`} role="presentation" onMouseDown={requestClose}>
      <aside ref={dialogRef} tabIndex={-1} className={tw("product-editor")} role="dialog" aria-label={product ? 'Edit product' : 'Add product'} aria-modal="true" onKeyDown={(event) => { if (event.key === 'Escape') requestClose(); }} onMouseDown={(event) => event.stopPropagation()}>
        <div className="sticky -top-6 z-10 bg-white py-3"><h2>{product ? 'Edit product' : 'Add product'}</h2><button type="button" aria-label="Close editor" onClick={requestClose}><X /></button></div>
        {product ? <Link className="text-sm text-brand underline" target="_blank" to={`/product-preview/${product.slug}`}>Preview saved product</Link> : null}
        <form onSubmit={handleSubmit((values) => save.mutate(values))}>
          <label>Product name<input required {...register('name')}/></label>
          <div className={tw("editor-row")}><label>SKU<input required {...register('sku')}/></label><label>Brand<input {...register('brand')}/></label></div>
          <label>Category<AdminSelect {...register('category', { valueAsNumber: true })}>{categories.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</AdminSelect></label>
          <label>Licensing role<AdminSelect {...register('licensing_role')}><option value="standard">Standard product</option><option value="licensed_product">Licensed product</option><option value="license_product">License product</option></AdminSelect></label>
          {licensingRole === 'licensed_product' ? <label>Required license product<AdminSelect required {...register('required_license_product_id', { valueAsNumber: true })}><option value="">Select license product</option>{licenseProducts.filter((item) => item.id !== product?.id).map((item) => <option value={item.id} key={item.id}>{item.name} ({item.sku})</option>)}</AdminSelect></label> : null}
          {licensingRole === 'license_product' ? <div className={tw("editor-row")}><label>Capacity supplied<input type="number" min="1" required {...register('license_capacity')}/></label><label>Term in days<input type="number" min="1" required {...register('license_term_days')}/></label></div> : null}
          <div className={tw("editor-row")}><label>Price<input type="number" min="0" step="0.01" required {...register('price')}/></label><label>Sale price<input type="number" min="0" step="0.01" {...register('sale_price')}/></label></div>
          <div className={tw("editor-row")}><label>Bulk from quantity<input type="number" min="2" step="1" {...register('bulk_minimum_quantity')}/></label><label>Bulk unit price<input type="number" min="0.01" step="0.01" {...register('bulk_unit_price')}/></label></div>
          <div className={tw("editor-row")}><label>Cost price<input type="number" min="0" step="0.01" {...register('cost_price')}/></label><label>Stock quantity<input type="number" min="0" {...register('inventory_quantity', { valueAsNumber: true })}/></label></div>
          <label>Short description<input {...register('short_description')}/></label>
          <label>Description<textarea rows={4} {...register('description')}/></label>
          <fieldset className={tw("product-specification-editor")}>
            <legend>Product highlights and specifications</legend>
            <p>{specifications.filter((item) => item.show_in_highlights).length} / 4 highlights selected</p>
            {specifications.length ? <div className={tw("product-specification-list")}>
              {specifications.map((specification, index) => <article key={specification.id}>
                <span>{index + 1}</span>
                <label>Label<input required maxLength={120} value={specification.key} onChange={(event) => updateSpecification(specification.id, 'key', event.target.value)}/></label>
                <label>Value<input required maxLength={255} value={specification.value} onChange={(event) => updateSpecification(specification.id, 'value', event.target.value)}/></label>
                <label className="!col-start-2 !flex items-center gap-2"><input className="!size-4 !min-h-0" type="checkbox" checked={specification.show_in_highlights} disabled={!specification.show_in_highlights && specifications.filter((item) => item.show_in_highlights).length >= 4} onChange={(event) => setSpecifications((current) => current.map((item) => item.id === specification.id ? { ...item, show_in_highlights: event.target.checked } : item))} />Highlight</label>
                <div className={tw("product-specification-actions")}>
                  <button type="button" title="Move up" aria-label={`Move specification ${index + 1} up`} disabled={index === 0} onClick={() => moveSpecification(index, -1)}><ArrowUp size={15}/></button>
                  <button type="button" title="Move down" aria-label={`Move specification ${index + 1} down`} disabled={index === specifications.length - 1} onClick={() => moveSpecification(index, 1)}><ArrowDown size={15}/></button>
                  <button className={tw("danger")} type="button" title="Remove specification" aria-label={`Remove specification ${index + 1}`} onClick={() => setSpecifications((current) => current.filter((item) => item.id !== specification.id))}><Trash2 size={15}/></button>
                </div>
              </article>)}
            </div> : <div className={tw("product-specification-empty")}><span>No specifications added. The highlight banner will stay hidden.</span></div>}
            <button className={tw("action-button action-button-secondary w-full")} type="button" onClick={() => setSpecifications((current) => [...current, { id: crypto.randomUUID(), key: '', value: '', show_in_highlights: false }])}><Plus size={16}/>Add specification</button>
          </fieldset>
          {defaultsQuery.data ? <ProductPresentationEditor layout={layout} onLayoutChange={setLayout} defaults={defaultsQuery.data.product_presentation_defaults} overrides={overrides} onChange={setOverrides} /> : <p role="status">{defaultsQuery.isError ? 'Could not load content defaults.' : 'Loading content defaults...'}</p>}
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
          <div className={`${tw("editor-actions")} sticky -bottom-6 border-t border-border bg-white py-4`}><button type="button" onClick={requestClose}>Cancel</button><button className={tw("admin-primary")} type="submit" disabled={save.isPending || !defaultsQuery.data}>{save.isPending ? 'Saving...' : 'Save product'}</button></div>
        </form>
      </aside>
    </div>);
}
