import { useMemo, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Image, Pencil, Plus, Save, Settings2, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, ApiError, mediaUrl, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { Banner, SiteSettings } from '../../../types'
import { AdminErrorState } from '../components/AdminErrorState'

type BannerForm = Omit<Banner, 'id'>

export function AdminSiteSettingsPage() {
  const queryClient = useQueryClient()
  const [editingBanner, setEditingBanner] = useState<Banner | 'new' | null>(null)
  const settingsQuery = useQuery({ queryKey: ['admin-site-settings'], queryFn: api.adminSiteSettings })
  const bannersQuery = useQuery({ queryKey: ['banners'], queryFn: api.banners })
  const banners = useMemo(
    () => (bannersQuery.data ? unwrap(bannersQuery.data) : []),
    [bannersQuery.data],
  )
  const deleteBanner = useMutation({
    mutationFn: api.deleteBanner,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['banners'] })
      toast.success('Banner deleted')
    },
    onError: () => toast.error('Could not delete banner'),
  })
  const toggleBanner = useMutation({
    mutationFn: (banner: Banner) => api.updateBanner(banner.id, { is_active: !banner.is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['banners'] })
      toast.success('Banner visibility updated')
    },
    onError: () => toast.error('Could not update banner visibility'),
  })

  if (settingsQuery.isError || bannersQuery.isError) return <AdminErrorState resource="site settings" />

  return (
    <main className={tw('admin-page')}>
      <div className={tw('admin-title-row')}>
        <div>
          <p className={tw('admin-breadcrumb')}>Workspace / Site settings</p>
          <h1>Site settings</h1>
          <p>Edit storefront identity, contact details, commerce defaults and homepage content.</p>
        </div>
      </div>

      {settingsQuery.data ? (
        <SiteSettingsForm settings={settingsQuery.data} />
      ) : (
        <section className={tw('admin-panel route-message')}>Loading site settings...</section>
      )}

      <section className={tw('admin-panel site-banner-panel')}>
        <div className={tw('panel-heading site-settings-heading')}>
          <div>
            <p className={tw('eyebrow')}>HOMEPAGE</p>
            <h2>Hero banners</h2>
            <p>The first active banner is displayed in the storefront hero.</p>
          </div>
          <button className={tw('admin-primary')} type="button" onClick={() => setEditingBanner('new')}>
            <Plus size={17} /> Add banner
          </button>
        </div>

        <div className={tw('admin-table-wrap')}>
          <table className={tw('admin-table banner-table')}>
            <thead>
              <tr><th>Banner</th><th>Call to action</th><th>Order</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {banners.length ? banners.map((banner) => (
                <tr key={banner.id}>
                  <td>
                    <div className={tw('banner-cell')}>
                      <span>{banner.image_url ? <img src={mediaUrl(banner.image_url)} alt="" /> : <Image size={18} />}</span>
                      <div><strong>{banner.title}</strong><small>{banner.subtitle || 'No subtitle'}</small></div>
                    </div>
                  </td>
                  <td>{banner.cta_label || 'No button'}</td>
                  <td>{banner.sort_order}</td>
                  <td><span className={tw(`status ${banner.is_active ? 'active' : 'inactive'}`)}>{banner.is_active ? 'Active' : 'Hidden'}</span></td>
                  <td>
                    <div className={tw('table-action-buttons')}>
                      <button type="button" title={banner.is_active ? 'Hide banner' : 'Publish banner'} aria-label={banner.is_active ? `Hide ${banner.title}` : `Publish ${banner.title}`} onClick={() => toggleBanner.mutate(banner)}>
                        {banner.is_active ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                      <button type="button" title="Edit banner" aria-label={`Edit ${banner.title}`} onClick={() => setEditingBanner(banner)}><Pencil size={16} /></button>
                      <button className={tw('danger-action')} type="button" title="Delete banner" aria-label={`Delete ${banner.title}`} onClick={() => {
                        if (window.confirm(`Delete “${banner.title}”?`)) deleteBanner.mutate(banner.id)
                      }}><Trash2 size={16} /></button>
                    </div>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={5}><div className={tw('admin-empty-row')}><Image size={24} /><strong>No hero banners yet</strong><span>Add a banner to manage the homepage hero content.</span></div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {editingBanner ? <BannerEditor banner={editingBanner === 'new' ? null : editingBanner} onClose={() => setEditingBanner(null)} /> : null}
    </main>
  )
}

function SiteSettingsForm({ settings }: { settings: SiteSettings }) {
  const queryClient = useQueryClient()
  const { register, handleSubmit, reset, control, formState: { isDirty } } = useForm<SiteSettings>({ defaultValues: settings })
  const commerceEnabled = useWatch({ control, name: 'commerce_defaults_enabled' })
  const bankTransferEnabled = useWatch({ control, name: 'bank_transfer_enabled' })
  const save = useMutation({
    mutationFn: api.updateSiteSettings,
    onSuccess: (value) => {
      queryClient.setQueryData(['admin-site-settings'], value)
      queryClient.invalidateQueries({ queryKey: ['site-settings'] })
      reset(value)
      toast.success('Site settings saved')
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : 'Could not save site settings. Check the entered values.'),
  })

  return (
    <form className={tw('site-settings-form')} onSubmit={handleSubmit((values) => save.mutate(values))}>
      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>Store identity</h2><p>Brand and customer support details used across the storefront.</p></div></div>
        <div className={tw('settings-fields two-column')}>
          <label>Site name<input required maxLength={255} {...register('site_name')} /></label>
          <label>Tagline<input maxLength={255} {...register('tagline')} /></label>
          <label>Support email<input type="email" {...register('support_email')} /></label>
          <label>Support phone<input maxLength={32} {...register('support_phone')} /></label>
          <label>Working hours<input maxLength={255} {...register('working_hours')} /></label>
          <label className={tw('field-wide')}>Company address<textarea rows={3} {...register('company_address')} /></label>
        </div>
      </section>

      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>Bank transfer invoices</h2><p>Details printed on quote invoices when manual bank transfer is available to customers.</p><label className={tw('settings-feature-toggle')}><input type="checkbox" {...register('bank_transfer_enabled')} /><span><strong>Include bank transfer instructions on invoices</strong><small>Also enable Bank transfer for customers in the Payments workspace.</small></span></label></div></div>
        <div className={tw(`settings-fields two-column ${bankTransferEnabled ? '' : 'settings-fields-disabled'}`)}>
          <label>Beneficiary name<input maxLength={255} disabled={!bankTransferEnabled} {...register('bank_beneficiary_name')} /></label>
          <label>Bank name<input maxLength={255} disabled={!bankTransferEnabled} {...register('bank_name')} /></label>
          <label>Account number<input maxLength={120} disabled={!bankTransferEnabled} {...register('bank_account_number')} /></label>
          <label>IBAN<input maxLength={64} disabled={!bankTransferEnabled} {...register('bank_iban')} /></label>
          <label>SWIFT / BIC<input maxLength={32} disabled={!bankTransferEnabled} {...register('bank_swift_bic')} /></label>
          <label className={tw('field-wide')}>Transfer instructions<textarea rows={3} disabled={!bankTransferEnabled} placeholder="Use the invoice number as the payment reference." {...register('bank_payment_instructions')} /></label>
        </div>
      </section>

      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>Commerce defaults</h2><p>Reference values for future tax and shipping calculations.</p><label className={tw('settings-feature-toggle')}><input type="checkbox" {...register('commerce_defaults_enabled')} /><span><strong>Enable commerce defaults</strong><small>Allow these values to be used by future checkout calculations.</small></span></label></div></div>
        <div className={tw(`settings-fields four-column ${commerceEnabled ? '' : 'settings-fields-disabled'}`)}>
          <label>Currency<input required maxLength={10} disabled={!commerceEnabled} {...register('default_currency')} /></label>
          <label>Tax rate (%)<input type="number" min="0" max="100" step="0.01" disabled={!commerceEnabled} {...register('tax_rate')} /></label>
          <label>Flat shipping<input type="number" min="0" step="0.01" disabled={!commerceEnabled} {...register('flat_shipping_rate')} /></label>
          <label>Free shipping from<input type="number" min="0" step="0.01" disabled={!commerceEnabled} {...register('free_shipping_minimum')} /></label>
        </div>
      </section>

      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>Homepage hero details</h2><p>Edit the secondary action and the three statistics below the hero message.</p></div></div>
        <div className={tw('settings-fields two-column')}>
          <label>Secondary button label<input maxLength={120} {...register('homepage_hero_secondary_cta_label')} /></label>
          <label>Secondary button link<input maxLength={500} {...register('homepage_hero_secondary_cta_url')} /></label>
        </div>
        <div className={tw('settings-repeat-grid three-column')}>
          {settings.homepage_hero_stats.map((_, index) => <div className={tw('settings-repeat-card')} key={`hero-stat-${index}`}><strong>Statistic {index + 1}</strong><label>Value<input maxLength={30} {...register(`homepage_hero_stats.${index}.value` as const)} /></label><label>Label<input maxLength={80} {...register(`homepage_hero_stats.${index}.label` as const)} /></label></div>)}
        </div>
      </section>

      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>GPS fleet section</h2><p>Edit the section heading, description and feature checklist.</p></div></div>
        <div className={tw('settings-fields two-column')}>
          <label>Eyebrow<input maxLength={255} {...register('homepage_solution_eyebrow')} /></label>
          <label>Heading<input maxLength={255} {...register('homepage_solution_title')} /></label>
          <label className={tw('field-wide')}>Description<textarea rows={4} {...register('homepage_solution_description')} /></label>
        </div>
        <div className={tw('settings-repeat-grid two-column')}>
          {settings.homepage_solution_benefits.map((_, index) => <label className={tw('settings-repeat-field')} key={`solution-benefit-${index}`}>Benefit {index + 1}<input maxLength={255} {...register(`homepage_solution_benefits.${index}` as const)} /></label>)}
        </div>
      </section>

      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>Radio comparison</h2><p>Edit the comparison heading and every value in the three product columns.</p></div></div>
        <div className={tw('settings-fields two-column')}>
          <label>Eyebrow<input maxLength={255} {...register('homepage_comparison_eyebrow')} /></label>
          <label>Heading<input maxLength={255} {...register('homepage_comparison_title')} /></label>
        </div>
        <div className={tw('settings-repeat-grid three-column')}>
          {settings.homepage_comparison_products.map((_, index) => <div className={tw('settings-repeat-card')} key={`comparison-${index}`}><strong>Product column {index + 1}</strong><label>Model<input {...register(`homepage_comparison_products.${index}.model` as const)} /></label><label>Best for<input {...register(`homepage_comparison_products.${index}.best_for` as const)} /></label><label>Network<input {...register(`homepage_comparison_products.${index}.network` as const)} /></label><label>System<input {...register(`homepage_comparison_products.${index}.system` as const)} /></label><label>Protection<input {...register(`homepage_comparison_products.${index}.protection` as const)} /></label><label>From / price<input {...register(`homepage_comparison_products.${index}.price` as const)} /></label></div>)}
        </div>
      </section>

      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>Resource cards</h2><p>Edit the resource section heading, images, descriptions and optional links.</p></div></div>
        <div className={tw('settings-fields two-column')}>
          <label>Eyebrow<input maxLength={255} {...register('homepage_resources_eyebrow')} /></label>
          <label>Heading<input maxLength={255} {...register('homepage_resources_title')} /></label>
        </div>
        <div className={tw('settings-repeat-grid three-column')}>
          {settings.homepage_resources.map((resource, index) => <div className={tw('settings-repeat-card')} key={`resource-${index}`}>{resource.image_url ? <img className={tw('settings-resource-preview')} src={mediaUrl(resource.image_url)} alt="" /> : null}<strong>Resource {index + 1}</strong><label>Eyebrow<input {...register(`homepage_resources.${index}.eyebrow` as const)} /></label><label>Title<textarea rows={2} {...register(`homepage_resources.${index}.title` as const)} /></label><label>Description<textarea rows={3} {...register(`homepage_resources.${index}.description` as const)} /></label><label>Image URL<input {...register(`homepage_resources.${index}.image_url` as const)} /></label><label>Link<input {...register(`homepage_resources.${index}.url` as const)} /></label></div>)}
        </div>
      </section>

      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>Homepage contact banner</h2><p>Edit the final blue guidance banner and its action.</p></div></div>
        <div className={tw('settings-fields two-column')}>
          <label>Eyebrow<input maxLength={255} {...register('homepage_contact_eyebrow')} /></label>
          <label>Heading<input maxLength={255} {...register('homepage_contact_title')} /></label>
          <label className={tw('field-wide')}>Description<textarea rows={3} {...register('homepage_contact_description')} /></label>
          <label>Button label<input maxLength={120} {...register('homepage_contact_cta_label')} /></label>
          <label>Button link<input maxLength={500} placeholder="Leave empty to use support email" {...register('homepage_contact_cta_url')} /></label>
        </div>
      </section>

      <section className={tw('admin-panel settings-section')}>
        <div className={tw('settings-section-title')}><Settings2 size={19} /><div><h2>Company content</h2><p>About content, social links and default search metadata.</p></div></div>
        <div className={tw('settings-fields two-column')}>
          <label>Facebook URL<input type="url" {...register('facebook_url')} /></label>
          <label>LinkedIn URL<input type="url" {...register('linkedin_url')} /></label>
          <label>Instagram URL<input type="url" {...register('instagram_url')} /></label>
          <label>X / Twitter URL<input type="url" {...register('twitter_url')} /></label>
          <label className={tw('field-wide')}>About story<textarea rows={4} {...register('about_story')} /></label>
          <label>Mission<textarea rows={3} {...register('about_mission')} /></label>
          <label>Vision<textarea rows={3} {...register('about_vision')} /></label>
          <label className={tw('field-wide')}>About image URL<input maxLength={500} {...register('about_image_url')} /></label>
          <label>Meta title<input maxLength={255} {...register('meta_title')} /></label>
          <label>Meta description<textarea rows={3} {...register('meta_description')} /></label>
        </div>
      </section>

      <div className={tw('settings-save-bar')}>
        <span>{isDirty ? 'You have unsaved changes.' : 'All changes are saved.'}</span>
        <button className={tw('admin-primary')} type="submit" disabled={save.isPending || !isDirty}><Save size={17} />{save.isPending ? 'Saving...' : 'Save settings'}</button>
      </div>
    </form>
  )
}

function BannerEditor({ banner, onClose }: { banner: Banner | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { register, handleSubmit, control } = useForm<BannerForm>({
    defaultValues: banner ?? {
      title: '', subtitle: '', description: '', cta_label: 'Shop radios', cta_url: '/shop',
      image_url: '/images/hero-radio.png', sort_order: 0, is_active: true,
    },
  })
  const imageUrl = useWatch({ control, name: 'image_url' })
  const save = useMutation({
    mutationFn: (values: BannerForm) => banner ? api.updateBanner(banner.id, values) : api.createBanner(values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['banners'] })
      toast.success(banner ? 'Banner saved' : 'Banner created')
      onClose()
    },
    onError: () => toast.error('Could not save banner. Check the entered values.'),
  })

  return (
    <div className={tw('editor-backdrop')} role="presentation" onMouseDown={onClose}>
      <aside className={tw('product-editor banner-editor')} role="dialog" aria-modal="true" aria-labelledby="banner-editor-title" onMouseDown={(event) => event.stopPropagation()}>
        <div><h2 id="banner-editor-title">{banner ? 'Edit banner' : 'Add banner'}</h2><button type="button" aria-label="Close banner editor" onClick={onClose}><X /></button></div>
        <form onSubmit={handleSubmit((values) => save.mutate(values))}>
          {imageUrl ? <div className={tw('banner-preview')}><img src={mediaUrl(imageUrl)} alt="Banner preview" /></div> : null}
          <label>Title<input required maxLength={255} {...register('title')} /></label>
          <label>Subtitle<input maxLength={255} {...register('subtitle')} /></label>
          <label>Description<textarea rows={4} {...register('description')} /></label>
          <div className={tw('editor-row')}><label>Button label<input maxLength={120} {...register('cta_label')} /></label><label>Button link<input maxLength={500} {...register('cta_url')} /></label></div>
          <label>Image URL<input maxLength={500} {...register('image_url')} /></label>
          <label>Display order<input type="number" min="0" {...register('sort_order', { valueAsNumber: true })} /></label>
          <label className={tw('editor-check')}><input type="checkbox" {...register('is_active')} />Banner is active</label>
          <div className={tw('editor-actions')}><button type="button" onClick={onClose}>Cancel</button><button className={tw('admin-primary')} type="submit" disabled={save.isPending}>{save.isPending ? 'Saving...' : 'Save banner'}</button></div>
        </form>
      </aside>
    </div>
  )
}
