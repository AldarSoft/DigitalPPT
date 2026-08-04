import type { SelectHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'
import { tw } from '../../../lib/tailwind-styles'

export function AdminSelect({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className={tw('admin-select')}>
      <select {...props}>{children}</select>
      <ChevronDown size={16} aria-hidden="true" />
    </span>
  )
}

