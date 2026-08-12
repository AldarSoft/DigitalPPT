import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { CalendarClock, ChevronRight, Download, Search, Trash2, UserPlus, Users, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { User } from '../../../types'
import { Metric } from '../components/Metric'
import { AdminErrorState } from '../components/AdminErrorState'
import { exportAdminReport } from '../utils/exportAdminReport'

export function AdminCustomersPage() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [editing, setEditing] = useState<User | 'new' | null>(null);
    const usersQuery = useQuery({ queryKey: ['admin-users'], queryFn: () => api.users('ordering=-created_at&page_size=100') });
    const customers = (usersQuery.data ? unwrap(usersQuery.data) : [])
        .filter((user) => user.is_customer && !user.is_staff)
        .filter((user) => !search || `${user.first_name} ${user.last_name} ${user.email} ${user.profile.company_name}`.toLowerCase().includes(search.toLowerCase()));
    const remove = useMutation({
        mutationFn: (user: User) => api.deleteUser(user.id),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin-users'] }); toast.success('Customer deleted'); },
        onError: () => toast.error('Could not delete customer'),
    });
    if (usersQuery.isError)
        return <AdminErrorState resource="customers" />;
    const thisMonth = customers.filter((user) => new Date(user.date_joined).getMonth() === new Date().getMonth()).length;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><p className={tw("admin-breadcrumb")}>Workspace / Customers</p><h1>Customer directory</h1><p>Manage customer accounts, contact details and access.</p></div><button className={tw("admin-primary")} type="button" onClick={() => setEditing('new')}><UserPlus size={18}/>Add customer</button></div>
      <section className={tw("admin-stats")}>
        <Metric label="Total customers" value={String(customers.length)} icon={Users}/>
        <Metric label="Active accounts" value={String(customers.filter((user) => user.is_active).length)} icon={UserPlus}/>
        <Metric label="New this month" value={String(thisMonth)} icon={CalendarClock}/>
        <Metric label="Inactive" value={String(customers.filter((user) => !user.is_active).length)} icon={X}/>
      </section>
      <section className={tw("admin-toolbar compact-toolbar")}><div><Search size={19}/><input placeholder="Search customers" value={search} onChange={(event) => setSearch(event.target.value)}/></div><button type="button" onClick={() => void exportAdminReport({ kind: 'customers', rows: customers })}><Download size={17}/>Export</button></section>
      <section className={tw("admin-panel admin-table-wrap")}>
        <table className={tw("admin-table")}>
          <thead><tr><th>Customer</th><th>Company</th><th>Phone</th><th>Joined</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>{customers.length ? customers.map((user) => <tr key={user.id}>
            <td><div className={tw("customer-cell")}><span>{`${user.first_name[0] ?? ''}${user.last_name[0] ?? ''}` || 'CU'}</span><div><strong>{user.first_name} {user.last_name}</strong><small>{user.email}</small></div></div></td>
            <td>{user.profile.company_name || '-'}</td><td>{user.phone_number || '-'}</td><td>{new Date(user.date_joined).toLocaleDateString()}</td><td><span className={tw(`status status-${user.is_active ? 'completed' : 'cancelled'}`)}>{user.is_active ? 'active' : 'inactive'}</span></td>
            <td><div className={tw("table-actions")}><button type="button" aria-label={`Edit ${user.email}`} onClick={() => setEditing(user)}><ChevronRight size={18}/></button><button type="button" aria-label={`Delete ${user.email}`} onClick={() => { if (confirm(`Delete ${user.email}?`))
            remove.mutate(user); }}><Trash2 size={17}/></button></div></td>
          </tr>) : <tr><td colSpan={6}>No customers found.</td></tr>}</tbody>
        </table>
      </section>
      {editing ? <CustomerEditor user={editing === 'new' ? null : editing} onClose={() => setEditing(null)}/> : null}
    </main>);
}
type CustomerForm = {
    email: string;
    first_name: string;
    last_name: string;
    phone_number: string;
    company_name: string;
    job_title: string;
    password: string;
    is_active: boolean;
};
function CustomerEditor({ user, onClose }: {
    user: User | null;
    onClose: () => void;
}) {
    const queryClient = useQueryClient();
    const { register, handleSubmit } = useForm<CustomerForm>({
        defaultValues: user ? {
            email: user.email,
            first_name: user.first_name,
            last_name: user.last_name,
            phone_number: user.phone_number,
            company_name: user.profile.company_name,
            job_title: user.profile.job_title,
            password: '',
            is_active: user.is_active,
        } : { is_active: true, password: '' },
    });
    const save = useMutation({
        mutationFn: (values: CustomerForm) => {
            const payload = {
                email: values.email,
                username: user?.username ?? `${values.email.split('@')[0].replaceAll(/[^a-zA-Z0-9_.-]/g, '')}-${Date.now()}`,
                first_name: values.first_name,
                last_name: values.last_name,
                phone_number: values.phone_number,
                is_customer: true,
                is_staff: false,
                is_active: values.is_active,
                profile: { company_name: values.company_name, job_title: values.job_title },
                ...(values.password ? { password: values.password } : {}),
            };
            return user ? api.updateUser(user.id, payload) : api.createUser(payload);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-users'] });
            toast.success(user ? 'Customer saved' : 'Customer created');
            onClose();
        },
        onError: () => toast.error('Could not save customer'),
    });
    return (<div className={tw("editor-backdrop")} role="presentation" onMouseDown={onClose}>
      <aside className={tw("product-editor")} role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div><h2>{user ? 'Edit customer' : 'Add customer'}</h2><button type="button" aria-label="Close editor" onClick={onClose}><X /></button></div>
        <form onSubmit={handleSubmit((values) => save.mutate(values))}>
          <label>Email<input type="email" required {...register('email')}/></label>
          <div className={tw("editor-row")}><label>First name<input required {...register('first_name')}/></label><label>Last name<input required {...register('last_name')}/></label></div>
          <label>Phone<input {...register('phone_number')}/></label>
          <div className={tw("editor-row")}><label>Company<input {...register('company_name')}/></label><label>Job title<input {...register('job_title')}/></label></div>
          <label>{user ? 'New password (optional)' : 'Temporary password'}<input type="password" minLength={8} required={!user} {...register('password')}/></label>
          <label className={tw("editor-check")}><input type="checkbox" {...register('is_active')}/>Account is active</label>
          <div className={tw("editor-actions")}><button type="button" onClick={onClose}>Cancel</button><button className={tw("admin-primary")} type="submit" disabled={save.isPending}>{save.isPending ? 'Saving...' : 'Save customer'}</button></div>
        </form>
      </aside>
    </div>);
}
