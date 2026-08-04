import { useState } from 'react'
import { BarChart3, Boxes, Download, Percent, Search, ShoppingCart } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { tw } from '../../../lib/tailwind-styles'
import { AdminSelect } from '../components/AdminSelect'
import { AdminErrorState } from '../components/AdminErrorState'
import { Metric } from '../components/Metric'
import { OrderRows } from '../components/OrderRows'
import { useAdminData } from '../hooks/useAdminData'
import { exportCsv } from '../utils/exportCsv'

export function AdminAnalyticsPage() {
    const data = useAdminData();
    const [search, setSearch] = useState('');
    const [status, setStatus] = useState('');
    const completed = data.orderList.filter((order) => order.status === 'completed');
    const revenue = completed.reduce((total, order) => total + Number(order.total), 0);
    const average = completed.length ? revenue / completed.length : 0;
    const filtered = data.orderList.filter((order) => (!search || `${order.order_number} ${order.customer_first_name} ${order.customer_last_name}`.toLowerCase().includes(search.toLowerCase())) &&
        (!status || order.status === status));
    const chartData = (() => {
        const months = Array.from({ length: 6 }, (_, offset) => {
            const date = new Date();
            date.setMonth(date.getMonth() - (5 - offset), 1);
            return { key: date.toISOString().slice(0, 7), month: date.toLocaleDateString(undefined, { month: 'short' }), revenue: 0 };
        });
        completed.forEach((order) => {
            const row = months.find((month) => month.key === order.created_at.slice(0, 7));
            if (row)
                row.revenue += Number(order.total);
        });
        return months;
    })();
    if (data.isError)
        return <AdminErrorState resource="analytics" />;
    return (<main className={tw("admin-page")}>
      <div className={tw("admin-title-row")}><div><p className={tw("admin-breadcrumb")}>Workspace / Analytics</p><h1>Business analytics</h1><p>Understand revenue, product demand and customer activity.</p></div><button type="button" onClick={() => exportCsv('digital-ptt-analytics.csv', filtered)}><Download size={18}/>Export report</button></div>
      <section className={tw("admin-stats")}>
        <Metric label="Revenue" value={`$${revenue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} icon={BarChart3}/>
        <Metric label="Orders" value={String(data.orderList.length)} icon={ShoppingCart}/>
        <Metric label="Completion rate" value={`${data.orderList.length ? Math.round((completed.length / data.orderList.length) * 100) : 0}%`} icon={Percent}/>
        <Metric label="Avg. order value" value={`$${average.toFixed(0)}`} icon={Boxes}/>
      </section>
      <section className={tw("admin-panel analytics-chart-panel")}>
        <div className={tw("panel-heading")}><h2>Revenue trend</h2><span>Last 6 months</span></div>
        <div className={tw("revenue-chart")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid vertical={false} stroke="#e5eaf1"/>
              <XAxis dataKey="month" axisLine={false} tickLine={false}/>
              <YAxis hide/>
              <Tooltip formatter={(value) => `$${Number(value).toFixed(2)}`}/>
              <Bar dataKey="revenue" fill="#0869f7" radius={[5, 5, 0, 0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
      <section className={tw("admin-panel analytics-orders")}>
        <div className={tw("orders-toolbar")}><h2>Performance overview</h2><div><Search size={18}/><input placeholder="Search order or customer" value={search} onChange={(event) => setSearch(event.target.value)}/></div><AdminSelect aria-label="Filter analytics by order status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All status</option><option value="pending">Pending</option><option value="processing">Processing</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></AdminSelect></div>
        <OrderRows orders={filtered.slice(0, 10)} compact/>
      </section>
    </main>);
}
