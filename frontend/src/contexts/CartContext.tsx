import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { toast } from 'sonner'
import type { CartItem, Product } from '../types'

interface CartContextValue {
  items: CartItem[]
  count: number
  subtotal: number
  add: (product: Product, quantity?: number) => void
  setQuantity: (productId: number, quantity: number) => void
  remove: (productId: number) => void
  clear: () => void
}

const STORAGE_KEY = 'digital-ptt-cart-v1'
const CartContext = createContext<CartContextValue | null>(null)

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartItem[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as CartItem[]
    } catch {
      return []
    }
  })

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  }, [items])

  const value = useMemo<CartContextValue>(() => ({
    items,
    count: items.reduce((total, item) => total + item.quantity, 0),
    subtotal: items.reduce(
      (total, item) => total + Number(item.product.current_price) * item.quantity,
      0,
    ),
    add(product, quantity = 1) {
      if (product.inventory_quantity < 1) {
        toast.error(`${product.name} is currently out of stock`)
        return
      }
      const safeQuantity = Math.min(Math.max(quantity, 1), product.inventory_quantity)
      setItems((current) => {
        const match = current.find((item) => item.product.id === product.id)
        if (match) {
          return current.map((item) =>
            item.product.id === product.id
              ? {
                  ...item,
                  quantity: Math.min(
                    item.quantity + safeQuantity,
                    product.inventory_quantity,
                  ),
                }
              : item,
          )
        }
        return [...current, { product, quantity: safeQuantity }]
      })
      toast.success(`${product.name} added to cart`)
    },
    setQuantity(productId, quantity) {
      setItems((current) =>
        current.map((item) =>
          item.product.id === productId
            ? {
                ...item,
                quantity: Math.max(
                  1,
                  Math.min(quantity, Math.max(item.product.inventory_quantity, 1)),
                ),
              }
            : item,
        ),
      )
    },
    remove(productId) {
      setItems((current) => current.filter((item) => item.product.id !== productId))
    },
    clear() {
      setItems([])
    },
  }), [items])

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useCart() {
  const context = useContext(CartContext)
  if (!context) throw new Error('useCart must be used inside CartProvider')
  return context
}
