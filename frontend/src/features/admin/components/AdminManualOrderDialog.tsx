import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Building2, Check, PackagePlus, Plus, Trash2, UserPlus, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '../../../lib/api'
import type { Order, Product } from '../../../types'

type Item = { productId: number; quantity: number }
type PaymentState = 'draft' | 'waiting_payment' | 'paid'

export function AdminManualOrderDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (order: Order) => void }) {
  const [customerMode, setCustomerMode] = useState<'existing' | 'new'>('existing')
  const [customerId, setCustomerId] = useState<number | ''>('')
  const [customer, setCustomer] = useState({ first: '', last: '', email: '', phone: '' })
  const [organizationMode, setOrganizationMode] = useState<'existing' | 'new'>('existing')
  const [organizationId, setOrganizationId] = useState<number | ''>('')
  const [organizationName, setOrganizationName] = useState('')
  const [items, setItems] = useState<Item[]>([])
  const [productId, setProductId] = useState<number | ''>('')
  const [paymentState, setPaymentState] = useState<PaymentState>('waiting_payment')
  const [paymentReference, setPaymentReference] = useState('')
  const [shipping, setShipping] = useState({ address: '', city: '', state: '', postal: '', country: '', fee: '0.00' })
  const [notes, setNotes] = useState('')
  const usersQuery = useQuery({ queryKey: ['admin-manual-order-users'], queryFn: () => api.users('ordering=first_name&page_size=100') })
  const productsQuery = useQuery({ queryKey: ['admin-manual-order-products'], queryFn: () => api.products('ordering=name&page_size=200') })
  const organizationsQuery = useQuery({
    queryKey: ['admin-manual-order-organizations', customerId],
    queryFn: () => api.adminLicenseOrganizations({ customer_id: Number(customerId), page_size: 100 }),
    enabled: customerMode === 'existing' && Boolean(customerId),
  })
  const users = (usersQuery.data ? unwrap(usersQuery.data) : []).filter((user) => user.is_active && !user.is_staff)
  const products = useMemo(() => productsQuery.data ? unwrap(productsQuery.data) : [], [productsQuery.data])
  const organizations = organizationsQuery.data?.results.filter((organization) => organization.status !== 'draft') ?? []
  const selected = useMemo(() => items.map((item) => ({ ...item, product: products.find((product) => product.id === item.productId) })).filter((item): item is Item & { product: Product } => Boolean(item.product)), [items, products])
  const needsShipping = selected.some((item) => item.product.is_stock_tracked)
  const estimate = selected.reduce((total, item) => {
    const unit = item.product.bulk_minimum_quantity && item.product.bulk_unit_price && item.quantity >= item.product.bulk_minimum_quantity ? item.product.bulk_unit_price : item.product.current_price
    return total + Number(unit) * item.quantity
  }, 0)
  const create = useMutation({
    mutationFn: () => api.createManualOrder({
      customer_mode: customerMode, customer_id: customerMode === 'existing' ? customerId : undefined,
      customer_first_name: customer.first, customer_last_name: customer.last, customer_email: customer.email, customer_phone: customer.phone,
      company_name: organizationName, organization_mode: customerMode === 'new' ? 'new' : organizationMode,
      organization_id: customerMode === 'existing' && organizationMode === 'existing' ? organizationId : undefined,
      organization_name: customerMode === 'new' || organizationMode === 'new' ? organizationName : undefined,
      shipping_address: needsShipping ? shipping.address : '', shipping_city: needsShipping ? shipping.city : '', shipping_state: needsShipping ? shipping.state : '',
      shipping_postal_code: needsShipping ? shipping.postal : '', shipping_country: needsShipping ? shipping.country : '', shipping_fee: needsShipping ? shipping.fee : '0.00',
      notes, payment_state: paymentState, payment_reference: paymentState === 'paid' ? paymentReference : '',
      items: items.map((item) => ({ product: item.productId, quantity: item.quantity })),
    }),
    onSuccess: (order) => { toast.success(order.status === 'draft' ? 'Draft order created' : order.is_paid ? 'Paid order created and provisioned' : 'Order created awaiting payment'); onCreated(order) },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not create the order'),
  })
  const addProduct = () => { if (!productId) return; setItems((current) => current.some((item) => item.productId === productId) ? current.map((item) => item.productId === productId ? { ...item, quantity: item.quantity + 1 } : item) : [...current, { productId, quantity: 1 }]); setProductId('') }
  const validCustomer = customerMode === 'existing' ? Boolean(customerId) : Boolean(customer.email && organizationName.trim())
  const validOrganization = customerMode === 'new' || organizationMode === 'new'
    ? Boolean(organizationName.trim())
    : organizations.some((organization) => organization.id === organizationId)
  const canSubmit = validCustomer && validOrganization && items.length > 0 && (paymentState !== 'paid' || paymentReference.trim())

  return <div className="fixed inset-0 z-100 grid place-items-center bg-[rgba(5,17,38,.5)] p-4" role="presentation" onMouseDown={() => { if (!create.isPending) onClose() }}><section className="max-h-[94vh] w-full max-w-5xl overflow-auto rounded-panel border border-border bg-white shadow-xl" role="dialog" aria-modal="true" aria-labelledby="manual-order-title" onMouseDown={(event) => event.stopPropagation()}>
    <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-border bg-white px-6 py-5"><div><p className="font-mono text-[10px] font-bold text-brand">ADMIN ORDER</p><h2 id="manual-order-title" className="mt-1 text-2xl">Create manual order</h2><p className="mt-1 text-sm text-muted">Prices, stock, and required license capacity are confirmed by the server.</p></div><IconButton label="Close" onClick={onClose}><X size={20} /></IconButton></header>
    <form className="grid gap-6 p-6" onSubmit={(event) => { event.preventDefault(); create.mutate() }}>
      <Section icon={<UserPlus size={19} />} title="Client account"><Mode value={customerMode} options={[['existing', 'Existing client'], ['new', 'Create client account']]} onChange={(value) => { setCustomerMode(value as 'existing' | 'new'); if (value === 'new') setOrganizationMode('new') }} />{customerMode === 'existing' ? <label className="grid gap-2 text-sm font-bold">Client<select className="control" required value={customerId} onChange={(event) => setCustomerId(Number(event.target.value))}><option value="">Select account</option>{users.map((user) => <option value={user.id} key={user.id}>{`${user.first_name} ${user.last_name}`.trim() || user.email} - {user.email}</option>)}</select></label> : <div className="grid gap-4 sm:grid-cols-2"><Input label="First name" value={customer.first} onChange={(first) => setCustomer((value) => ({ ...value, first }))} /><Input label="Last name" value={customer.last} onChange={(last) => setCustomer((value) => ({ ...value, last }))} /><Input label="Email" type="email" required value={customer.email} onChange={(email) => setCustomer((value) => ({ ...value, email }))} /><Input label="Phone" value={customer.phone} onChange={(phone) => setCustomer((value) => ({ ...value, phone }))} /><p className="sm:col-span-2 text-xs text-muted">The client receives a single-use link to choose their password.</p></div>}</Section>
      <Section icon={<Building2 size={19} />} title="Organization">{customerMode === 'existing' ? <Mode value={organizationMode} options={[['existing', 'Use existing organization'], ['new', 'Create organization']]} onChange={(value) => setOrganizationMode(value as 'existing' | 'new')} /> : null}{customerMode === 'existing' && organizationMode === 'existing' ? <><label className="grid gap-2 text-sm font-bold">Organization<select className="control" required value={organizationId} onChange={(event) => setOrganizationId(Number(event.target.value))}><option value="">Select active organization</option>{organizations.map((organization) => <option value={organization.id} key={organization.id}>{organization.name}</option>)}</select></label><p className="text-xs text-muted">The selected client must already belong to this organization.</p></> : <Input label="New organization name" required value={organizationName} onChange={setOrganizationName} />}</Section>
      <Section icon={<PackagePlus size={19} />} title="Products"><div className="flex gap-2"><select className="control min-w-0 flex-1" value={productId} onChange={(event) => setProductId(Number(event.target.value))}><option value="">Select product</option>{products.map((product) => <option value={product.id} key={product.id}>{product.name} - {product.sku}</option>)}</select><button className="inline-flex min-h-11 items-center gap-2 rounded-control border border-brand bg-white px-4 font-bold text-brand" type="button" onClick={addProduct}><Plus size={18} />Add</button></div><div className="divide-y divide-border rounded-control border border-border">{selected.length ? selected.map((item) => <div className="grid grid-cols-[1fr_100px_42px] items-center gap-3 p-3" key={item.productId}><div><strong className="block text-sm">{item.product.name}</strong><small className="text-muted">{item.product.sku} · ${Number(item.product.current_price).toFixed(2)}</small></div><input className="control text-center" min={1} max={999} type="number" value={item.quantity} onChange={(event) => setItems((current) => current.map((value) => value.productId === item.productId ? { ...value, quantity: Math.max(1, Number(event.target.value)) } : value))} /><IconButton label={`Remove ${item.product.name}`} danger onClick={() => setItems((current) => current.filter((value) => value.productId !== item.productId))}><Trash2 size={17} /></IconButton></div>) : <p className="p-5 text-center text-sm text-muted">Add at least one product.</p>}</div><div className="rounded-control bg-brand-soft px-3 py-2 text-xs text-brand">Required license products are added only when compatible capacity is unavailable.</div></Section>
      {needsShipping ? <Section icon={<PackagePlus size={19} />} title="Delivery"><div className="grid gap-4 sm:grid-cols-2"><Input label="Address" required value={shipping.address} onChange={(address) => setShipping((value) => ({ ...value, address }))} /><Input label="City" required value={shipping.city} onChange={(city) => setShipping((value) => ({ ...value, city }))} /><Input label="State / province" value={shipping.state} onChange={(state) => setShipping((value) => ({ ...value, state }))} /><Input label="Postal code" value={shipping.postal} onChange={(postal) => setShipping((value) => ({ ...value, postal }))} /><Input label="Country" required value={shipping.country} onChange={(country) => setShipping((value) => ({ ...value, country }))} /><Input label="Shipping fee (USD)" type="number" value={shipping.fee} onChange={(fee) => setShipping((value) => ({ ...value, fee }))} /></div></Section> : null}
      <Section icon={<Check size={19} />} title="Payment state"><Mode value={paymentState} options={[['draft', 'Admin Draft'], ['waiting_payment', 'Waiting for payment'], ['paid', 'Paid and verified']]} onChange={(value) => setPaymentState(value as PaymentState)} />{paymentState === 'paid' ? <><Input label="Bank payment reference" required value={paymentReference} onChange={setPaymentReference} /><div className="flex items-start gap-2 rounded-control border border-warning bg-warning-soft p-3 text-sm text-warning"><AlertTriangle className="mt-0.5 shrink-0" size={18} /><span>Confirm funds were received. This immediately provisions digital products and licenses.</span></div></> : null}<label className="grid gap-2 text-sm font-bold">Internal notes<textarea className="min-h-24 rounded-control border border-border-input p-3 font-normal" value={notes} onChange={(event) => setNotes(event.target.value)} /></label></Section>
      <footer className="sticky bottom-0 flex flex-wrap items-center justify-between gap-4 border-t border-border bg-white pt-5"><div><span className="text-xs text-muted">Selected product estimate</span><strong className="block text-xl">${estimate.toFixed(2)} USD</strong><small className="text-muted">Final total may include an automatic license and shipping.</small></div><div className="flex gap-3"><button className="min-h-11 rounded-control border border-border-input bg-white px-4 font-bold" type="button" onClick={onClose}>Cancel</button><button className="min-h-11 rounded-control border-0 bg-brand px-5 font-bold text-white disabled:opacity-55" disabled={!canSubmit || create.isPending} type="submit">{create.isPending ? 'Creating...' : paymentState === 'draft' ? 'Create Draft order' : paymentState === 'paid' ? 'Create paid order' : 'Create order'}</button></div></footer>
    </form>
  </section></div>
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) { return <fieldset className="grid gap-4 rounded-panel border border-border p-4"><legend className="px-2"><span className="inline-flex items-center gap-2 font-bold">{icon}{title}</span></legend>{children}</fieldset> }
function Mode({ value, options, onChange }: { value: string; options: readonly (readonly [string, string])[]; onChange: (value: string) => void }) { return <div className="inline-flex w-fit max-w-full overflow-auto rounded-control border border-border-input bg-surface-muted p-1">{options.map(([key, label]) => <button className={`min-h-9 whitespace-nowrap rounded-[4px] border-0 px-3 text-sm font-bold ${value === key ? 'bg-white text-brand shadow-sm' : 'bg-transparent text-muted'}`} type="button" key={key} onClick={() => onChange(key)}>{label}</button>)}</div> }
function Input({ label, value, onChange, type = 'text', required = false }: { label: string; value: string; onChange: (value: string) => void; type?: string; required?: boolean }) { return <label className="grid gap-2 text-sm font-bold">{label}<input className="control font-normal" type={type} required={required} value={value} onChange={(event) => onChange(event.target.value)} /></label> }
function IconButton({ label, children, danger = false, onClick }: { label: string; children: React.ReactNode; danger?: boolean; onClick: () => void }) { return <button className={`inline-flex size-10 items-center justify-center rounded-control border-0 ${danger ? 'bg-danger-soft text-danger' : 'bg-surface-muted text-ink'}`} type="button" aria-label={label} title={label} onClick={onClick}>{children}</button> }
