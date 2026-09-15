import { useState } from 'react'
import { ArrowDown, ArrowUp, ChevronDown, Plus, RotateCcw, Trash2 } from 'lucide-react'
import type { ProductContentIcon, ProductContentItem, ProductIntroduction, ProductLayout, ProductPresentation, ProductPresentationDefaults } from '../../../types'
import { ContentIcon, ProductAssurances } from '../../products/components/ProductContent'
import { contentIcons } from '../../../lib/product-content-icons'
import './product-presentation-editor.css'
import { AdminSelect } from './AdminSelect'

const rowButton = 'inline-flex size-10 shrink-0 items-center justify-center rounded-md border border-border bg-white text-muted hover:text-ink disabled:opacity-30 focus-visible:outline-2 focus-visible:outline-brand'

function IntroductionEditor({ value, onChange }: { value: ProductIntroduction; onChange: (value: ProductIntroduction) => void }) {
  return <div className="grid min-w-0 gap-3">
    <label className="!flex items-center gap-2"><input className="!size-4 !min-h-0" type="checkbox" checked={value.active} onChange={(e) => onChange({ ...value, active: e.target.checked })} />Visible</label>
    <label>Eyebrow<input maxLength={80} value={value.eyebrow} onChange={(e) => onChange({ ...value, eyebrow: e.target.value })} /></label>
    <label>Heading<input maxLength={160} value={value.heading} onChange={(e) => onChange({ ...value, heading: e.target.value })} /></label>
    <label>Description<textarea rows={3} maxLength={2000} placeholder="Product description" value={value.description} onChange={(e) => onChange({ ...value, description: e.target.value })} /></label>
    <label>Notice<textarea rows={2} maxLength={500} value={value.notice} onChange={(e) => onChange({ ...value, notice: e.target.value })} /></label>
  </div>
}

export function ContentListEditor({ items, onChange, assurances = false }: { items: ProductContentItem[]; onChange: (items: ProductContentItem[]) => void; assurances?: boolean }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const update = (index: number, patch: Partial<ProductContentItem>) => onChange(items.map((item, i) => i === index ? { ...item, ...patch } : item))
  const move = (index: number, direction: number) => {
    const next = [...items]
    ;[next[index], next[index + direction]] = [next[index + direction], next[index]]
    onChange(next)
  }
  return <div className="min-w-0 divide-y divide-border">
    {items.map((item, index) => <details key={item.id} className="group min-w-0 py-3" open={expandedId === item.id} onToggle={(event) => { const open = event.currentTarget.open; setExpandedId((current) => open ? item.id : current === item.id ? null : current) }}>
      <summary className="flex min-h-11 cursor-pointer items-center gap-3 text-sm"><span className="text-brand"><ContentIcon name={item.icon} size={20} /></span><span className="min-w-0 flex-1 break-words font-semibold">{item.title || 'New feature'}</span><span className="text-xs text-muted">{item.active ? 'Visible' : 'Hidden'}</span><ChevronDown size={16} className="shrink-0 text-muted group-open:rotate-180" /></summary>
      <div className="grid min-w-0 gap-3 pt-3">
        <div className="flex flex-wrap items-center gap-2"><label className="!flex flex-1 items-center gap-2"><input className="!size-4 !min-h-0" type="checkbox" checked={item.active} onChange={(e) => update(index, { active: e.target.checked })} />Visible</label><button className={rowButton} title="Move up" aria-label={`Move ${item.title} up`} type="button" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={16} /></button><button className={rowButton} title="Move down" aria-label={`Move ${item.title} down`} type="button" disabled={index === items.length - 1} onClick={() => move(index, 1)}><ArrowDown size={16} /></button>{!assurances ? <button className={rowButton} title="Remove" aria-label={`Remove ${item.title}`} type="button" onClick={() => onChange(items.filter((_, i) => i !== index))}><Trash2 size={16} /></button> : null}</div>
        <label>Icon<AdminSelect value={item.icon} onChange={(e) => update(index, { icon: e.target.value as ProductContentIcon })}>{Object.keys(contentIcons).map((icon) => <option key={icon} value={icon}>{icon.replaceAll('-', ' ')}</option>)}</AdminSelect></label>
        <label>Label<input required maxLength={80} value={item.title} onChange={(e) => update(index, { title: e.target.value })} /></label>
        <label>{assurances ? 'Details' : 'Description'}<textarea maxLength={500} rows={2} value={item.description} onChange={(e) => update(index, { description: e.target.value })} /></label>
        {assurances && item.id === 'payment' ? <span className="text-xs text-muted">Shown when live online payment is available.</span> : null}
      </div>
    </details>)}
    {!assurances ? <button className="mt-3 flex min-h-10 items-center gap-2 text-sm font-semibold text-brand disabled:opacity-40" type="button" disabled={items.length >= 8} onClick={() => { const id = crypto.randomUUID(); onChange([...items, { id, icon: 'info', title: '', description: '', active: true }]); setExpandedId(id) }}><Plus size={16} />Add feature</button> : null}
  </div>
}

export function ProductPresentationEditor({ layout, onLayoutChange, defaults, overrides, onChange }: { layout: ProductLayout; onLayoutChange: (layout: ProductLayout) => void; defaults: ProductPresentationDefaults; overrides: Partial<ProductPresentation>; onChange: (value: Partial<ProductPresentation>) => void }) {
  const effective: ProductPresentation = { ...defaults[layout], assurances: defaults.assurances, ...overrides }
  const reset = (section: keyof ProductPresentation) => {
    if (!window.confirm('Reset this section to site defaults?')) return
    const next = { ...overrides }
    delete next[section]
    onChange(next)
  }
  return <section className="presentation-editor min-w-0 border-t border-border pt-5">
    <h3 className="text-lg font-bold">Storefront presentation</h3>
    <label className="mt-4">Content template<AdminSelect value={layout} onChange={(e) => onLayoutChange(e.target.value as ProductLayout)}><option value="radio">Radio</option><option value="license">License</option><option value="accessory">Accessory</option></AdminSelect></label>
    {(['intro', 'features', 'assurances'] as const).map((section) => <section key={section} className="mt-4 min-w-0 border-t border-border pt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-bold">{section === 'intro' ? 'Introduction' : section === 'features' ? 'Features' : 'Information badges'}</h4><span className="text-xs text-muted">{overrides[section] === undefined ? 'Site default' : 'Customized'}</span></div>
      {overrides[section] === undefined ? <button type="button" className="mb-3 text-sm font-semibold text-brand" onClick={() => onChange({ ...overrides, [section]: structuredClone(effective[section]) })}>Customize</button> : <button type="button" className="mb-3 inline-flex items-center gap-1 text-sm text-muted" onClick={() => reset(section)}><RotateCcw size={14} />Reset to defaults</button>}
      <fieldset disabled={overrides[section] === undefined} className="min-w-0 disabled:opacity-65">
        {section === 'intro' ? <IntroductionEditor value={effective.intro} onChange={(intro) => onChange({ ...overrides, intro })} /> : <ContentListEditor assurances={section === 'assurances'} items={effective[section]} onChange={(items) => onChange({ ...overrides, [section]: items })} />}
      </fieldset>
    </section>)}
    <details className="mt-5 border-t border-border pt-3"><summary className="cursor-pointer text-sm font-semibold">Badge preview</summary><ProductAssurances items={effective.assurances.filter((item) => item.active)} /></details>
  </section>
}

export function PresentationDefaultsEditor({ value, onChange }: { value: ProductPresentationDefaults; onChange: (value: ProductPresentationDefaults) => void }) {
  const [layout, setLayout] = useState<ProductLayout>('radio')
  return <section className="presentation-editor min-w-0 max-w-3xl border-t border-border py-6">
    <h2 className="text-lg font-bold">Product page defaults</h2>
    <h3 className="mt-5 text-sm font-semibold">Information badges</h3>
    <ContentListEditor assurances items={value.assurances} onChange={(assurances) => onChange({ ...value, assurances })} />
    <div className="my-5 flex gap-1 border-b border-border" role="tablist" aria-label="Product templates">{(['radio', 'license', 'accessory'] as const).map((key) => <button className={`min-h-11 px-4 text-sm capitalize ${layout === key ? 'border-b-2 border-brand font-bold text-brand' : 'text-muted'}`} role="tab" aria-selected={layout === key} type="button" key={key} onClick={() => setLayout(key)}>{key}</button>)}</div>
    <IntroductionEditor value={value[layout].intro} onChange={(intro) => onChange({ ...value, [layout]: { ...value[layout], intro } })} />
    <h3 className="mt-5 text-sm font-semibold">Features</h3>
    <ContentListEditor items={value[layout].features} onChange={(features) => onChange({ ...value, [layout]: { ...value[layout], features } })} />
  </section>
}
