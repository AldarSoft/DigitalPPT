import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { CalendarClock, ChevronRight, Download, Percent, Plus, Search, Tag, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { Promotion } from '../../../types'
import { AdminSelect } from '../components/AdminSelect'
import { AdminErrorState } from '../components/AdminErrorState'
import { Metric } from '../components/Metric'
import { exportCsv } from '../utils/exportCsv'

export function AdminPromotionsPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [editing, setEditing] = useState<Promotion | 'new' | null>(null);
    const promotionsQuery = useQuery({ queryKey: ['admin-promotions'], queryFn: () => api.promotions('ordering=-created_at&page_size=100') });
    const promotions = (promotionsQuery.data ? unwrap(promotionsQuery.data) : []).filter((promotion) => !search || `${promotion.code} ${promotion.title}`.toLowerCase().includes(search.toLowerCase()));
    const remove = useMutation({
        mutationFn: (promotion: Promotion) => api.deletePromotion(promotion.id),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-promotions'] }); toast.success('Promotion deleted'); },
        onError: () => toast.error('Could not delete promotion'),
    });
    const toggle = useMutation({
        mutationFn: (promotion: Promotion) => api.updatePromotion(promotion.id, { is_active: !promotion.is_active }),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-promotions'] }); toast.success('Promotion status updated'); },
        onError: () => toast.error('Could not update promotion'),
    });
    if (promotionsQuery.isError)
        return <AdminErrorState resource="promotions" />;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><p className={tw("admin-breadcrumb")}>Workspace / Promotions</p><h1>Promotions</h1><p>Create and monitor discounts, campaigns and promotional offers.</p></div><button className={tw("admin-primary")} type="button" onClick={() => setEditing('new')}><Plus size={18}/>Create promotion</button></div>
      <section className={tw("admin-stats")}>
        <Metric label="Active campaigns" value={String(promotions.filter((item) => item.status === 'active').length)} icon={Tag}/>
        <Metric label="Scheduled" value={String(promotions.filter((item) => item.status === 'scheduled').length)} icon={CalendarClock}/>
        <Metric label="Redeemed" value={String(promotions.reduce((total, item) => total + item.times_redeemed, 0))} icon={Percent}/>
        <Metric label="Expired" value={String(promotions.filter((item) => item.status === 'expired').length)} icon={X}/>
      </section>
      <section className={tw("admin-toolbar compact-toolbar")}><div><Search size={19}/><input placeholder="Search code or campaign" value={search} onChange={(event) => setSearch(event.target.value)}/></div><button type="button" onClick={() => exportCsv('digital-ptt-promotions.csv', promotions)}><Download size={17}/>Export</button></section>
      <section className={tw("admin-panel admin-table-wrap")}>
        <table className={tw("admin-table")}><thead><tr><th>Promotion</th><th>Discount</th><th>Schedule</th><th>Redeemed</th><th>Status</th><th>Action</th></tr></thead><tbody>{promotions.length ? promotions.map((promotion) => <tr key={promotion.id}>
          <td><div className={tw("promotion-cell")}><Tag size={18}/><span><strong>{promotion.title}</strong><small>{promotion.code}</small></span></div></td><td>{promotion.discount_type === 'percentage' ? `${Number(promotion.discount_value)}%` : `$${Number(promotion.discount_value).toFixed(2)}`}</td><td>{promotion.starts_at ? new Date(promotion.starts_at).toLocaleDateString() : 'Now'} - {promotion.ends_at ? new Date(promotion.ends_at).toLocaleDateString() : 'Open'}</td><td>{promotion.times_redeemed}{promotion.usage_limit ? ` / ${promotion.usage_limit}` : ''}</td><td><button className={tw(`status status-${promotion.status === 'active' ? 'completed' : promotion.status === 'expired' ? 'cancelled' : 'pending'} status-button`)} type="button" onClick={() => toggle.mutate(promotion)}>{promotion.status}</button></td><td><div className={tw("table-actions")}><button type="button" aria-label={`Edit ${promotion.title}`} onClick={() => setEditing(promotion)}><ChevronRight size={18}/></button><button type="button" aria-label={`Delete ${promotion.title}`} onClick={() => { if (confirm(`Delete ${promotion.title}?`))
            remove.mutate(promotion); }}><Trash2 size={17}/></button></div></td>
        </tr>) : <tr><td colSpan={6}>No promotions found. Create the first campaign.</td></tr>}</tbody></table>
      </section>
      {editing ? <PromotionEditor promotion={editing === 'new' ? null : editing} onClose={() => setEditing(null)}/> : null}
    </main>);
}
type PromotionForm = {
    code: string;
    title: string;
    description: string;
    discount_type: Promotion['discount_type'];
    discount_value: string;
    starts_at: string;
    ends_at: string;
    usage_limit: number | null;
    is_active: boolean;
};
function toLocalInput(value: string | null) {
    if (!value)
        return '';
    const date = new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function PromotionEditor({ promotion, onClose }: {
    promotion: Promotion | null;
    onClose: () => void;
}) {
    const queryClient = useQueryClient();
    const { register, handleSubmit } = useForm<PromotionForm>({
        defaultValues: promotion ? {
            code: promotion.code,
            title: promotion.title,
            description: promotion.description,
            discount_type: promotion.discount_type,
            discount_value: promotion.discount_value,
            starts_at: toLocalInput(promotion.starts_at),
            ends_at: toLocalInput(promotion.ends_at),
            usage_limit: promotion.usage_limit,
            is_active: promotion.is_active,
        } : { discount_type: 'percentage', discount_value: '10', is_active: true, starts_at: '', ends_at: '', usage_limit: null },
    });
    const save = useMutation({
        mutationFn: (values: PromotionForm) => {
            const payload = {
                ...values,
                code: values.code.trim().toUpperCase(),
                starts_at: values.starts_at ? new Date(values.starts_at).toISOString() : null,
                ends_at: values.ends_at ? new Date(values.ends_at).toISOString() : null,
                usage_limit: values.usage_limit || null,
            };
            return promotion ? api.updatePromotion(promotion.id, payload) : api.createPromotion(payload);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-promotions'] });
            toast.success(promotion ? 'Promotion saved' : 'Promotion created');
            onClose();
        },
        onError: () => toast.error('Could not save promotion. Check the code and dates.'),
    });
    return (<div className={tw("editor-backdrop")} role="presentation" onMouseDown={onClose}><aside className={tw("product-editor")} role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
      <div><h2>{promotion ? 'Edit promotion' : 'Create promotion'}</h2><button type="button" aria-label="Close editor" onClick={onClose}><X /></button></div>
      <form onSubmit={handleSubmit((values) => save.mutate(values))}>
        <div className={tw("editor-row")}><label>Code<input required {...register('code')}/></label><label>Campaign title<input required {...register('title')}/></label></div>
        <label>Description<textarea rows={3} {...register('description')}/></label>
        <div className={tw("editor-row")}><label>Discount type<AdminSelect {...register('discount_type')}><option value="percentage">Percentage</option><option value="fixed">Fixed amount</option></AdminSelect></label><label>Discount value<input type="number" min="0.01" step="0.01" required {...register('discount_value')}/></label></div>
        <div className={tw("editor-row")}><label>Starts<input type="datetime-local" {...register('starts_at')}/></label><label>Ends<input type="datetime-local" {...register('ends_at')}/></label></div>
        <label>Usage limit<input type="number" min="1" {...register('usage_limit', { setValueAs: (value) => value === '' ? null : Number(value) })}/></label>
        <label className={tw("editor-check")}><input type="checkbox" {...register('is_active')}/>Promotion is active</label>
        <div className={tw("editor-actions")}><button type="button" onClick={onClose}>Cancel</button><button className={tw("admin-primary")} type="submit" disabled={save.isPending}>{save.isPending ? 'Saving...' : 'Save promotion'}</button></div>
      </form>
    </aside></div>);
}
