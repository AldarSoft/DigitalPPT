import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Search, SlidersHorizontal } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { SelectControl } from '../../../components/SelectControl'
import { Pagination } from '../../../components/Pagination'
import { ProductCard } from '../components/ProductCard'
import { api, unwrap } from '../../../lib/api'
import { catalogRequestState } from '../../../lib/catalog-request-state'
import { tw } from '../../../lib/tailwind-styles'

const PAGE_SIZE = 12

const ORDERING_MAP: Record<string, string> = {
    featured: '-is_featured,-created_at',
    price: 'current_price_value',
    '-price': '-current_price_value',
    '-created_at': '-created_at',
}

export function ShopPage() {
    const [params, setParams] = useSearchParams();
    const [search, setSearch] = useState(params.get('search') ?? '');
    const category = params.get('category') ?? '';
    const ordering = params.get('ordering') ?? 'featured';
    const inStock = params.get('stock') === 'true';
    const requestedPage = Number(params.get('page') ?? '1');
    const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
    const categoriesQuery = useQuery({
        queryKey: ['categories'],
        queryFn: api.categories,
    });
    const productsQuery = useQuery({
        queryKey: ['products', params.toString()],
        queryFn: () => {
            const query = new URLSearchParams(params);
            query.set('ordering', ORDERING_MAP[ordering] ?? ORDERING_MAP.featured);
            if (inStock) {
                query.set('stock', 'true');
            } else {
                query.delete('stock');
            }
            if (params.get('price_min')) {
                query.set('min_price', params.get('price_min') ?? '');
                query.delete('price_min');
            }
            if (params.get('price_max')) {
                query.set('max_price', params.get('price_max') ?? '');
                query.delete('price_max');
            }
            query.set('page', String(page));
            query.set('page_size', String(PAGE_SIZE));
            return api.products(query.toString());
        },
        placeholderData: keepPreviousData,
    });
    const priceBoundsQuery = useQuery({
        queryKey: ['product-price-bounds', category, params.get('search') ?? '', inStock],
        queryFn: async () => {
            const base = new URLSearchParams(params);
            for (const key of ['page', 'ordering', 'price_min', 'price_max'])
                base.delete(key);
            base.set('page_size', '1');
            const minimumQuery = new URLSearchParams(base);
            const maximumQuery = new URLSearchParams(base);
            minimumQuery.set('ordering', 'current_price_value');
            maximumQuery.set('ordering', '-current_price_value');
            const [minimumResult, maximumResult] = await Promise.all([
                api.products(minimumQuery.toString()),
                api.products(maximumQuery.toString()),
            ]);
            return {
                min: Number(unwrap(minimumResult)[0]?.current_price ?? 0),
                max: Number(unwrap(maximumResult)[0]?.current_price ?? 0),
            };
        },
    });
    const categories = categoriesQuery.data ? unwrap(categoriesQuery.data) : [];
    const selectedCategory = categories.find((item) => item.slug === category);
    const showCategoryDropdown = categories.length > 6;
    const rawProducts = useMemo(() => {
        return productsQuery.data ? unwrap(productsQuery.data) : [];
    }, [productsQuery.data]);
    const priceRange = useMemo(() => {
        if (priceBoundsQuery.data)
            return priceBoundsQuery.data;
        return { min: 0, max: 0 };
    }, [priceBoundsQuery.data]);
    const parseNumericParam = (value: string | null, fallback: number) => {
        const parsed = Number(value);
        return value !== null && !Number.isNaN(parsed) ? parsed : fallback;
    };
    const clampPrice = (value: number) => Math.min(Math.max(value, priceRange.min), priceRange.max);
    const priceMinParam = clampPrice(parseNumericParam(params.get('price_min'), priceRange.min));
    const priceMaxParam = clampPrice(parseNumericParam(params.get('price_max'), priceRange.max));
    const priceMin = Math.min(priceMinParam, priceMaxParam);
    const priceMax = Math.max(priceMinParam, priceMaxParam);
    const priceSpan = priceRange.max - priceRange.min;
    const priceMinPercent = priceSpan ? ((priceMin - priceRange.min) / priceSpan) * 100 : 0;
    const priceMaxPercent = priceSpan ? ((priceMax - priceRange.min) / priceSpan) * 100 : 100;
    const catalogHero = category === 'poc-radios' ? {
        eyebrow: 'CONNECTED TEAM COMMUNICATION',
        title: 'Professional radios for work without range limits.',
        copy: '4G LTE, Android and dual-mode radios for connected teams in the field.',
        image: '/images/radio-810.png',
        alt: 'Professional Android push-to-talk radio',
    } : category === 'radio-holsters' ? {
        eyebrow: 'FIELD-READY ACCESSORIES',
        title: 'Carry your radio. Keep your hands free.',
        copy: 'Chest packs and secure carry systems for teams that work on the move.',
        image: '/images/holsters-hero.png',
        alt: 'Professional radio holsters and chest harness systems',
    } : {
        eyebrow: 'DIGITAL PTT CATALOG',
        title: 'Communication gear built for the field.',
        copy: 'Radios, connected systems and secure carry options for professional teams.',
        image: '/images/radio-810.png',
        alt: 'Professional Digital PTT radio equipment',
    };
    const products = useMemo(() => {
        let list = rawProducts;
        const searchTerm = (params.get('search') ?? '').trim().toLowerCase();
        if (category) {
            list = list.filter((product) => product.category.slug === category);
        }
        if (inStock) {
            list = list.filter((product) => product.is_stock_tracked === false || product.inventory_quantity > 0);
        }
        list = list.filter((product) => {
            const price = Number(product.current_price);
            const matchesSearch = !searchTerm || [product.name, product.sku, product.category.name]
                .some((value) => value.toLowerCase().includes(searchTerm));
            return price >= priceMin && price <= priceMax && matchesSearch;
        });
        if (ordering === 'price') {
            list = [...list].sort((a, b) => Number(a.current_price) - Number(b.current_price));
        }
        if (ordering === '-price') {
            list = [...list].sort((a, b) => Number(b.current_price) - Number(a.current_price));
        }
        if (ordering === 'featured') {
            list = [...list].sort((a, b) => Number(b.is_featured) - Number(a.is_featured));
        }
        return list;
    }, [rawProducts, category, inStock, ordering, priceMin, priceMax, params]);
    const requestState = catalogRequestState({
        hasData: Boolean(productsQuery.data),
        isError: productsQuery.isError,
        isLoading: productsQuery.isLoading,
    });
    const totalProducts = productsQuery.data && !Array.isArray(productsQuery.data)
            ? productsQuery.data.count
            : products.length;
    const setParam = (key: string, value: string, defaultValue?: string) => {
        const next = new URLSearchParams(params);
        if (!value || value === defaultValue)
            next.delete(key);
        else
            next.set(key, value);
        if (key !== 'page')
            next.delete('page');
        setParams(next);
    };
    return (<main className={tw("catalog-page")}>
      <section className={tw("catalog-hero")}>
        <div className={tw("shell catalog-hero-grid")}>
          <div>
            <p className={tw("eyebrow light")}>{catalogHero.eyebrow}</p>
            <h1>{catalogHero.title}</h1>
            <p>{catalogHero.copy}</p>
            <div className={tw("catalog-pills")}>
              <span>{totalProducts} field options</span>
              <span>{selectedCategory?.name ?? 'Live inventory'}</span>
            </div>
          </div>
          <img src={catalogHero.image} alt={catalogHero.alt}/>
        </div>
      </section>

      <section className={tw("catalog-main shell")}>
        <div className={tw("catalog-heading")}>
          <div><p className={tw("eyebrow")}>SHOP THE CATALOG</p><h2>Built to work. Ready to ship.</h2></div>
          <SelectControl className="catalog-sort-select" value={ordering} onChange={(event) => setParam('ordering', event.target.value)} aria-label="Sort products">
            <option value="featured">Featured</option>
            <option value="price">Price: low to high</option>
            <option value="-price">Price: high to low</option>
            <option value="-created_at">Newest</option>
          </SelectControl>
        </div>

        <form className={tw("catalog-search")} onSubmit={(event) => {
            event.preventDefault();
            setParam('search', search.trim());
        }}>
          <Search size={20}/>
          <input aria-label="Search products" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by product, SKU or category"/>
          <button type="submit">Search</button>
        </form>

        <div className={tw("catalog-layout")}>
          <aside className={tw("catalog-filters")}>
            <div><SlidersHorizontal size={19}/><strong>Filters</strong></div>
            {showCategoryDropdown ? (<label className={tw("category-select")}>
                Category
                <SelectControl className="category-dropdown-select" value={category} onChange={(event) => setParam('category', event.target.value)}>
                  <option value="">All categories</option>
                  {categories.map((item) => <option value={item.slug} key={item.id}>{item.name}</option>)}
                </SelectControl>
              </label>) : (<fieldset className={tw("category-filter")}>
                <legend>Category</legend>
                <div>
                  <label>
                    <input type="checkbox" name="category" value="" checked={!category} onChange={() => setParam('category', '')}/>
                    <span>All categories</span>
                  </label>
                  {categories.map((item) => (<label key={item.id}>
                      <input type="checkbox" name="category" value={item.slug} checked={category === item.slug} onChange={(event) => setParam('category', event.target.checked ? item.slug : '')}/>
                      <span>{item.name}</span>
                    </label>))}
                </div>
              </fieldset>)}
            <fieldset className={tw("price-filter")}>
              <legend className={tw("price-filter-header")}>Price range</legend>
              <div className={tw("price-filter-values")}>
                <span>Min <strong>${priceMin}</strong></span>
                <span>Max <strong>${priceMax}</strong></span>
              </div>
              <div className={tw("price-range")}>
                <span className={tw("price-range-track")}/>
                <span
                  className={tw("price-range-active")}
                  style={{ left: `${priceMinPercent}%`, right: `${100 - priceMaxPercent}%` }}
                />
                <label>
                  <span className="sr-only">Minimum price</span>
                  <input
                    type="range"
                    aria-label="Minimum price"
                    min={priceRange.min}
                    max={priceRange.max}
                    step={1}
                    value={priceMinParam}
                    disabled={!priceSpan}
                    onChange={(event) => {
                        const nextMin = Math.min(Number(event.target.value), priceMaxParam);
                        setParam('price_min', String(nextMin), String(priceRange.min));
                    }}
                  />
                </label>
                <label>
                  <span className="sr-only">Maximum price</span>
                  <input
                    type="range"
                    aria-label="Maximum price"
                    min={priceRange.min}
                    max={priceRange.max}
                    step={1}
                    value={priceMaxParam}
                    disabled={!priceSpan}
                    onChange={(event) => {
                        const nextMax = Math.max(Number(event.target.value), priceMinParam);
                        setParam('price_max', String(nextMax), String(priceRange.max));
                    }}
                  />
                </label>
              </div>
            </fieldset>
            <label className={tw("check-row")}>
              <input type="checkbox" checked={inStock} onChange={(event) => setParam('stock', event.target.checked ? 'true' : '')}/>
              <span>In stock only</span>
            </label>
            <button type="button" onClick={() => { setParams({}); setSearch(''); }}>Clear filters</button>
          </aside>

          <div>
            {requestState === 'unavailable' ? (<div className={tw("empty-state")} role="alert">
                <AlertTriangle size={30}/><h3>Catalog temporarily unavailable</h3><p>We could not load current products, prices, or availability. Please try again.</p>
                <button className={tw("primary-action")} type="button" onClick={() => void Promise.all([productsQuery.refetch(), categoriesQuery.refetch(), priceBoundsQuery.refetch()])}>Try again</button>
              </div>) : requestState === 'loading' ? (<div className={tw("empty-state")}><Search size={30}/><h3>Loading catalog</h3><p>Fetching the latest product availability.</p></div>) : products.length ? (<>
                <div className={tw("catalog-grid")}>
                  {products.map((product) => <ProductCard product={product} key={product.id}/>)}
                </div>
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={totalProducts}
                  loading={productsQuery.isFetching}
                  className="mt-5"
                  onPageChange={(nextPage) => setParam('page', String(nextPage), '1')}
                />
              </>) : (<div className={tw("empty-state")}><Search size={30}/><h3>No products found</h3><p>Try clearing a filter or using a broader search.</p></div>)}
          </div>
        </div>
      </section>
    </main>);
}
