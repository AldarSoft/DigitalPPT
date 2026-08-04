import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, SlidersHorizontal } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { SelectControl } from '../../../components/SelectControl'
import { ProductCard } from '../components/ProductCard'
import { api, unwrap } from '../../../lib/api'
import { fallbackCategories, fallbackProducts } from '../../../lib/fallback-data'
import { tw } from '../../../lib/tailwind-styles'

export function ShopPage() {
    const [params, setParams] = useSearchParams();
    const [search, setSearch] = useState(params.get('search') ?? '');
    const category = params.get('category') ?? '';
    const ordering = params.get('ordering') ?? 'featured';
    const inStock = params.get('stock') === 'true';
    const categoriesQuery = useQuery({
        queryKey: ['categories'],
        queryFn: api.categories,
    });
    const productsQuery = useQuery({
        queryKey: ['products', params.toString()],
        queryFn: () => {
            const query = new URLSearchParams(params);
            if (ordering === 'featured') {
                query.delete('ordering');
                query.delete('featured');
            }
            query.delete('stock');
            return api.products(query.toString());
        },
    });
    const categories = categoriesQuery.data ? unwrap(categoriesQuery.data) : fallbackCategories;
    const selectedCategory = categories.find((item) => item.slug === category);
    const showCategoryDropdown = categories.length > 6;
    const rawProducts = useMemo(
        () => productsQuery.data ? unwrap(productsQuery.data) : fallbackProducts,
        [productsQuery.data],
    );
    const priceRange = useMemo(() => {
        const prices = rawProducts.map((product) => Number(product.current_price)).filter((price) => Number.isFinite(price));
        return {
            min: prices.length ? Math.min(...prices) : 0,
            max: prices.length ? Math.max(...prices) : 0,
        };
    }, [rawProducts]);
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
        if (category)
            list = list.filter((product) => product.category.slug === category);
        if (inStock)
            list = list.filter((product) => product.inventory_quantity > 0);
        list = list.filter((product) => {
            const price = Number(product.current_price);
            return price >= priceMin && price <= priceMax;
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
    }, [rawProducts, category, inStock, ordering, priceMin, priceMax]);
    const setParam = (key: string, value: string, defaultValue?: string) => {
        const next = new URLSearchParams(params);
        if (!value || value === defaultValue)
            next.delete(key);
        else
            next.set(key, value);
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
              <span>{products.length} field options</span>
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
                    onChange={(event) => {
                        const nextMin = Math.min(Number(event.target.value), priceMaxParam);
                        setParam('price_min', String(nextMin), String(priceRange.min));
                        if (nextMin > priceMaxParam)
                            setParam('price_max', String(nextMin), String(priceRange.max));
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
                    onChange={(event) => {
                        const nextMax = Math.max(Number(event.target.value), priceMinParam);
                        setParam('price_max', String(nextMax), String(priceRange.max));
                        if (nextMax < priceMinParam)
                            setParam('price_min', String(nextMax), String(priceRange.min));
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
            {productsQuery.isError ? (<p className={tw("connection-note")}>Showing the built-in development catalog while the Django API is offline.</p>) : null}
            {products.length ? (<div className={tw("catalog-grid")}>
                {products.map((product) => <ProductCard product={product} key={product.id}/>)}
              </div>) : (<div className={tw("empty-state")}><Search size={30}/><h3>No products found</h3><p>Try clearing a filter or using a broader search.</p></div>)}
          </div>
        </div>
      </section>
    </main>);
}
