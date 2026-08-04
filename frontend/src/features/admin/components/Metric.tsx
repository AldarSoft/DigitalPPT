import type { LucideIcon } from 'lucide-react'

export function Metric({ label, value, icon: Icon, note }: {
  label: string
  value: string
  icon: LucideIcon
  note?: string
}) {
  return <article><p>{label.toUpperCase()}</p><Icon size={21}/><strong>{value}</strong>{note ? <span>{note}</span> : null}</article>
}

