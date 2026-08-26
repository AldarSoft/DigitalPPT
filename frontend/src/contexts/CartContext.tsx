import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { toast } from 'sonner'
import { api } from '../lib/api'
import { refreshPersistedCartProducts } from '../lib/catalog-validation'
import { unitPriceForQuantity } from '../lib/pricing'
import type { CartItem, Product } from '../types'
import { useAuth } from './AuthContext'

interface CartContextValue {
  items: CartItem[]
  count: number
  subtotal: number
  isCatalogRefreshing: boolean
  catalogRefreshError: boolean
  isLicenseCalculating: boolean
  licenseCalculationError: boolean
  retryCatalogRefresh: () => void
  add: (product: Product, quantity?: number) => void
  setQuantity: (productId: number, quantity: number) => void
  remove: (productId: number) => void
  clear: () => void
}

const STORAGE_KEY = 'digital-ptt-cart-v1'
const MAX_QUOTE_QUANTITY = 1000
const CartContext = createContext<CartContextValue | null>(null)

interface LicenseCalculation {
  signature: string
  automaticItems: CartItem[]
  error: boolean
}

export function CartProvider({ children }: { children: ReactNode }) {
  const auth = useAuth()
  const [manualItems, setManualItems] = useState<CartItem[]>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as CartItem[]
      return stored.filter((item) => !item.is_automatic)
    } catch {
      return []
    }
  })
  const [storedProductsRefreshed, setStoredProductsRefreshed] = useState(
    () => manualItems.length === 0,
  )
  const [catalogRefreshError, setCatalogRefreshError] = useState(false)
  const [licenseCalculation, setLicenseCalculation] = useState<LicenseCalculation>({
    signature: '',
    automaticItems: [],
    error: false,
  })
  const needsLicensing = manualItems.some(
    (item) => item.product.licensing_role === 'licensed_product',
  )
  const calculationSignature = `${auth.ready ? auth.user?.id ?? 'anonymous' : 'loading'}:${manualItems
    .map((item) => `${item.product.id}:${item.quantity}`)
    .join('|')}`
  const calculationIsCurrent = licenseCalculation.signature === calculationSignature
  const isLicenseCalculating = needsLicensing && (!auth.ready || !calculationIsCurrent)
  const licenseCalculationError = needsLicensing
    && calculationIsCurrent
    && licenseCalculation.error
  const items = useMemo(
    () => [
      ...manualItems,
      ...(needsLicensing && calculationIsCurrent
        ? licenseCalculation.automaticItems
        : []),
    ],
    [calculationIsCurrent, licenseCalculation.automaticItems, manualItems, needsLicensing],
  )

  useEffect(() => {
    if (storedProductsRefreshed) return

    let active = true
    refreshPersistedCartProducts(manualItems, api.product).then(({ productsById, unavailableProductIds }) => {
      if (!active) return
      if (!unavailableProductIds.length) {
        setManualItems((current) => current.map((item) => {
          const product = productsById.get(item.product.id)
          return product ? { ...item, product } : item
        }))
      }
      setCatalogRefreshError(unavailableProductIds.length > 0)
      setStoredProductsRefreshed(true)
    })

    return () => {
      active = false
    }
  }, [manualItems, storedProductsRefreshed])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(manualItems))
  }, [manualItems])

  useEffect(() => {
    if (!needsLicensing || !auth.ready) return

    let active = true
    const timer = window.setTimeout(() => {
      api.cartCapacity(
        manualItems.map(({ product, quantity }) => ({ product: product.id, quantity })),
      )
        .then((response) => {
          if (!active) return
          setLicenseCalculation({
            signature: calculationSignature,
            automaticItems: response.requirements
              .filter((requirement) => requirement.automatic_license_units > 0)
              .map((requirement) => ({
                product: requirement.license_product,
                quantity: requirement.automatic_license_units,
                is_automatic: true,
                covered_quantity: requirement.covered_quantity,
                uncovered_quantity: requirement.uncovered_quantity,
                required_for_product_names: requirement.product_quantities.map(
                  (item) => item.product_name,
                ),
              })),
            error: false,
          })
        })
        .catch(() => {
          if (!active) return
          setLicenseCalculation({
            signature: calculationSignature,
            automaticItems: [],
            error: true,
          })
        })
    }, 150)

    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [auth.ready, calculationSignature, manualItems, needsLicensing])

  const value = useMemo<CartContextValue>(() => ({
    items,
    count: items.reduce((total, item) => total + item.quantity, 0),
    subtotal: items.reduce(
      (total, item) => total + unitPriceForQuantity(item.product, item.quantity) * item.quantity,
      0,
    ),
    isCatalogRefreshing: !storedProductsRefreshed,
    catalogRefreshError,
    isLicenseCalculating,
    licenseCalculationError,
    retryCatalogRefresh() {
      setCatalogRefreshError(false)
      setStoredProductsRefreshed(false)
    },
    add(product, quantity = 1) {
      if (product.is_stock_tracked !== false && product.inventory_quantity < 1) {
        toast.error(`${product.name} is currently out of stock`)
        return
      }
      const safeQuantity = Math.min(Math.max(quantity, 1), MAX_QUOTE_QUANTITY)
      setManualItems((current) => {
        const match = current.find((item) => item.product.id === product.id)
        if (match) {
          return current.map((item) =>
            item.product.id === product.id
              ? {
                  ...item,
                  quantity: Math.min(
                    item.quantity + safeQuantity,
                    MAX_QUOTE_QUANTITY,
                  ),
                }
              : item,
          )
        }
        return [...current, { product, quantity: safeQuantity }]
      })
      if (!catalogRefreshError) setStoredProductsRefreshed(true)
      toast.success(`${product.name} added to cart`)
    },
    setQuantity(productId, quantity) {
      setManualItems((current) =>
        current.map((item) =>
          item.product.id === productId
            ? {
                ...item,
                quantity: Math.max(
                  1,
                  Math.min(quantity, MAX_QUOTE_QUANTITY),
                ),
              }
            : item,
        ),
      )
    },
    remove(productId) {
      const removesLastManualItem = manualItems.filter((item) => item.product.id !== productId).length === 0
      setManualItems((current) => current.filter((item) => item.product.id !== productId))
      if (removesLastManualItem) {
        setCatalogRefreshError(false)
        setStoredProductsRefreshed(true)
      }
    },
    clear() {
      setManualItems([])
      setCatalogRefreshError(false)
      setStoredProductsRefreshed(true)
    },
  }), [catalogRefreshError, isLicenseCalculating, items, licenseCalculationError, manualItems, storedProductsRefreshed])

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useCart() {
  const context = useContext(CartContext)
  if (!context) throw new Error('useCart must be used inside CartProvider')
  return context
}
