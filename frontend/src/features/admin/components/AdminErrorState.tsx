import { AlertCircle } from 'lucide-react'
import { tw } from '../../../lib/tailwind-styles'

export function AdminErrorState({ resource }: { resource: string }) {
  return (
    <main className={tw('admin-page')}>
      <section className={tw('admin-panel route-message')} role="alert">
        <AlertCircle size={28} />
        <h1>Could not load {resource}</h1>
        <p>Check the API connection and refresh this page to try again.</p>
      </section>
    </main>
  )
}
