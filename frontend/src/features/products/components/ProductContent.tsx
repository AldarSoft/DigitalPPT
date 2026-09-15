import { useState } from 'react'
import { Info } from 'lucide-react'
import type { ProductContentIcon, ProductContentItem, ProductPresentation } from '../../../types'
import { tw } from '../../../lib/tailwind-styles'

import { contentIcons } from '../../../lib/product-content-icons'

export function ContentIcon({ name, size = 22 }: { name: ProductContentIcon; size?: number }) {
  const Icon = contentIcons[name] ?? Info
  return <Icon size={size} aria-hidden="true" />
}

export function ProductAssurances({ items }: { items: ProductContentItem[] }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  if (!items.length) return null
  return <div className="mt-3 min-w-0">
    <div className="grid gap-2 sm:grid-cols-[repeat(auto-fit,minmax(100px,1fr))]">
      {items.map((item) => item.description ? <button key={item.id} type="button" aria-expanded={expanded === item.id} onClick={() => setExpanded(expanded === item.id ? null : item.id)} className="flex min-h-20 min-w-0 items-center justify-center gap-2 rounded-lg bg-surface-muted px-3 py-3 text-brand transition-colors hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-brand sm:flex-col">
        <ContentIcon name={item.icon} /><span className="break-words text-center text-xs font-bold text-ink">{item.title}</span>
      </button> : <div key={item.id} className="flex min-h-20 min-w-0 flex-col items-center justify-center gap-2 rounded-lg bg-surface-muted p-3 text-brand"><ContentIcon name={item.icon} /><span className="break-words text-center text-xs font-bold text-ink">{item.title}</span></div>)}
    </div>
    {items.find((item) => item.id === expanded)?.description ? <p role="status" className="mt-2 break-words border-l-2 border-brand px-3 py-2 text-sm text-muted">{items.find((item) => item.id === expanded)?.description}</p> : null}
  </div>
}

export function ProductMarketing({ content, description }: { content: ProductPresentation; description: string }) {
  const features = content.features.filter((item) => item.active)
  const intro = content.intro
  if (!intro.active && !features.length) return null
  return <section className={tw('product-features')}>
    <div className={`mx-auto grid max-w-[1440px] gap-8 px-6 ${intro.active && features.length ? 'lg:grid-cols-2 lg:gap-16' : ''}`}>
      {intro.active ? <div className="min-w-0 break-words">
        {intro.eyebrow ? <p className={tw('eyebrow')}>{intro.eyebrow}</p> : null}
        {intro.heading ? <h2 className="mt-4 text-3xl font-bold leading-tight md:text-4xl">{intro.heading}</h2> : null}
        {intro.description || description ? <p className="mt-5 whitespace-pre-line text-base leading-7 text-muted">{intro.description || description}</p> : null}
        {intro.notice ? <div className={tw('product-notice')}><Info className="shrink-0" size={21} /><span>{intro.notice}</span></div> : null}
      </div> : null}
      {features.length ? <div className={tw('product-feature-list')}>{features.map((item) => <div className={tw('product-feature-item')} key={item.id}><span><ContentIcon name={item.icon} /></span><div className="break-words"><strong>{item.title}</strong><small>{item.description}</small></div></div>)}</div> : null}
    </div>
  </section>
}
