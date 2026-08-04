import type { SelectHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'
import { tw } from '../lib/tailwind-styles'

export function SelectControl({ children, className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className={tw(`select-control ${className}`)}>
      <select {...props}>{children}</select>
      <ChevronDown size={17} strokeWidth={2} aria-hidden="true" />
    </span>
  )
}
