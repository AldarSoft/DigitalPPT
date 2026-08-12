import { ChevronLeft, ChevronRight } from 'lucide-react'
import { tw } from '../lib/tailwind-styles'

export function Pagination({
  page,
  pageSize,
  total,
  loading,
  className,
  onPageChange,
}: {
  page: number
  pageSize: number
  total: number
  loading?: boolean
  className?: string
  onPageChange: (page: number) => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const firstItem = total ? (page - 1) * pageSize + 1 : 0
  const lastItem = Math.min(page * pageSize, total)

  if (total <= pageSize) return null

  return (
    <nav className={tw('pagination', className)} aria-label="List pagination">
      <p>Showing {firstItem}-{lastItem} of {total}</p>
      <div>
        <button
          type="button"
          disabled={loading || page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft size={16} />
          <span>Previous</span>
        </button>
        <strong>Page {page} of {pageCount}</strong>
        <button
          type="button"
          disabled={loading || page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          <span>Next</span>
          <ChevronRight size={16} />
        </button>
      </div>
    </nav>
  )
}
