import { ArrowRight, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import { tw } from '../lib/tailwind-styles'

export function NotFoundPage() {
  return (
    <main className={tw('route-message shell')}>
      <Search size={32} />
      <h1>Page not found</h1>
      <p>The page may have moved or the address may be incorrect.</p>
      <Link className={tw('primary-action')} to="/shop">
        Browse the catalog <ArrowRight size={17} />
      </Link>
    </main>
  )
}

